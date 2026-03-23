
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio

router = APIRouter()

clients = set()

async def broadcast_ws_message(message: dict):
    """Send a message to all connected WebSocket clients."""
    to_remove = set()
    for ws in clients:
        try:
            await ws.send_json(message)
        except Exception:
            to_remove.add(ws)
    for ws in to_remove:
        clients.discard(ws)

@router.websocket("/ws/stream")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            await asyncio.sleep(60)  # Keep connection alive, real events will be pushed
    except WebSocketDisconnect:
        clients.discard(ws)
