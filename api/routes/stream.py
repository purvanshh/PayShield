import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

active_connections: list[WebSocket] = []


@router.websocket("/v1/stream")
async def stream_alerts(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("action") == "subscribe":
                await websocket.send_json({"status": "subscribed", "channel": "alerts"})
    except WebSocketDisconnect:
        active_connections.remove(websocket)
    except Exception:
        if websocket in active_connections:
            active_connections.remove(websocket)


async def broadcast_alert(alert: dict):
    dead = []
    for conn in active_connections:
        try:
            await conn.send_json(alert)
        except Exception:
            dead.append(conn)
    for conn in dead:
        if conn in active_connections:
            active_connections.remove(conn)
