from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = {}

    def register(self, run_id: str, ws: WebSocket) -> None:
        self._connections.setdefault(run_id, set()).add(ws)

    def unregister(self, run_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(run_id)
        if conns is not None:
            conns.discard(ws)
            if not conns:
                self._connections.pop(run_id, None)

    async def broadcast(self, run_id: str, payload: dict) -> None:
        conns = list(self._connections.get(run_id, ()))
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001 - a dead connection must not break the broadcast to others
                self.unregister(run_id, ws)


manager = ConnectionManager()
