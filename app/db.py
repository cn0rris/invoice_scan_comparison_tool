import asyncio
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from app.config import settings


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self._write_lock = asyncio.Lock()

    async def connect(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        schema_sql = (Path(__file__).parent / "schema.sql").read_text()
        await self._conn.executescript(schema_sql)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database not connected"
        return self._conn

    # --- runs ---

    async def create_run(
        self, run_id: str, prompt_text: str, invoice_dir: str, ground_truth_dir: str, models: list[str]
    ) -> None:
        async with self._write_lock:
            await self.conn.execute(
                """INSERT INTO runs (id, created_at, status, prompt_text, invoice_dir,
                       ground_truth_dir, models_json, total_pairs, completed_pairs)
                   VALUES (?, ?, 'pending', ?, ?, ?, ?, 0, 0)""",
                (run_id, now_iso(), prompt_text, invoice_dir, ground_truth_dir, json.dumps(models)),
            )
            await self.conn.commit()

    async def set_run_running(self, run_id: str, total_pairs: int) -> None:
        async with self._write_lock:
            await self.conn.execute(
                "UPDATE runs SET status='running', started_at=?, total_pairs=? WHERE id=?",
                (now_iso(), total_pairs, run_id),
            )
            await self.conn.commit()

    async def finish_run(self, run_id: str, status: str, error_message: Optional[str] = None) -> None:
        async with self._write_lock:
            await self.conn.execute(
                "UPDATE runs SET status=?, completed_at=?, error_message=? WHERE id=?",
                (status, now_iso(), error_message, run_id),
            )
            await self.conn.commit()

    async def get_run(self, run_id: str) -> Optional[dict]:
        cur = await self.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def list_runs(self, limit: int = 50) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # --- results ---

    async def insert_pending_results(self, run_id: str, pairs: list[dict]) -> list[dict]:
        """pairs: list of {model_id, invoice_stem, invoice_filename, ground_truth_json (str|None)}.
        Returns the inserted rows (with generated ids) in the same order."""
        rows = []
        async with self._write_lock:
            for pair in pairs:
                result_id = new_id()
                status = "pending" if pair["ground_truth_json"] is not None else "no_ground_truth"
                await self.conn.execute(
                    """INSERT INTO results (id, run_id, model_id, invoice_stem, invoice_filename,
                           status, ground_truth_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        result_id,
                        run_id,
                        pair["model_id"],
                        pair["invoice_stem"],
                        pair["invoice_filename"],
                        status,
                        pair["ground_truth_json"],
                    ),
                )
                rows.append({"id": result_id, "status": status, **pair})
            await self.conn.commit()
        return rows

    async def mark_result_running(self, result_id: str) -> None:
        async with self._write_lock:
            await self.conn.execute(
                "UPDATE results SET status='running', started_at=? WHERE id=?",
                (now_iso(), result_id),
            )
            await self.conn.commit()

    async def complete_result(
        self,
        result_id: str,
        run_id: str,
        *,
        status: str,
        raw_output: Optional[str],
        parsed_json: Optional[str],
        diff_json: Optional[str],
        mistake_count: Optional[int],
        error_message: Optional[str],
        duration_ms: Optional[int],
    ) -> None:
        async with self._write_lock:
            await self.conn.execute(
                """UPDATE results SET status=?, raw_output=?, parsed_json=?, diff_json=?,
                       mistake_count=?, error_message=?, completed_at=?, duration_ms=?
                   WHERE id=?""",
                (
                    status,
                    raw_output,
                    parsed_json,
                    diff_json,
                    mistake_count,
                    error_message,
                    now_iso(),
                    duration_ms,
                    result_id,
                ),
            )
            await self.conn.execute(
                "UPDATE runs SET completed_pairs = completed_pairs + 1 WHERE id=?", (run_id,)
            )
            await self.conn.commit()

    async def get_results_for_run(self, run_id: str) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT * FROM results WHERE run_id=? ORDER BY invoice_stem, model_id", (run_id,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


db = Database(settings.db_path)


def compute_summary(run: dict, results: list[dict]) -> dict[str, Any]:
    """Shared aggregation used by both the orchestrator's run_complete broadcast
    and the GET /api/runs/{id}/summary endpoint, so the two can't drift."""
    per_model: dict[str, dict[str, int]] = {}
    matrix: dict[str, dict[str, Optional[int]]] = {}
    for r in results:
        model_id = r["model_id"]
        invoice_stem = r["invoice_stem"]
        per_model.setdefault(model_id, {"total_mistakes": 0, "success": 0, "error": 0})
        matrix.setdefault(invoice_stem, {})
        if r["status"] == "success":
            per_model[model_id]["success"] += 1
            per_model[model_id]["total_mistakes"] += r["mistake_count"] or 0
            matrix[invoice_stem][model_id] = r["mistake_count"]
        elif r["status"] in ("error", "no_ground_truth"):
            per_model[model_id]["error"] += 1
            matrix[invoice_stem][model_id] = None
        else:
            matrix[invoice_stem][model_id] = None
    return {
        "run_id": run["id"],
        "status": run["status"],
        "per_model": per_model,
        "matrix": matrix,
    }
