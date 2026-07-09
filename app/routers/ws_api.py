from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db import compute_summary, db
from app.orchestrator.ws_manager import manager

router = APIRouter()


@router.websocket("/ws/runs/{run_id}")
async def run_events(websocket: WebSocket, run_id: str):
    await websocket.accept()
    manager.register(run_id, websocket)
    try:
        run = await db.get_run(run_id)
        if run is None:
            await websocket.send_json({"type": "error", "message": "Run not found"})
            await websocket.close()
            return
        results = await db.get_results_for_run(run_id)
        snapshot = {"type": "snapshot", "run": run, "results": results}
        if run["status"] in ("completed", "failed"):
            snapshot["summary"] = compute_summary(run, results)
        await websocket.send_json(snapshot)

        while True:
            # This endpoint is broadcast-only; block on receive so we notice disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.unregister(run_id, websocket)
