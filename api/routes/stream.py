import asyncio
import json
import logging

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from api.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/v1/stream")
async def stream_alerts(websocket: WebSocket, token: str = Query("")):
    if not token:
        await websocket.close(code=1008, reason="missing_token")
        return
    try:
        from api.auth import AuthManager
        auth = AuthManager()
        principal = auth.verify_access_token(token)
        if principal is None:
            principal = auth.verify_api_key(token)
        if principal is None:
            await websocket.close(code=1008, reason="invalid_token")
            return
        client_id = f"{principal.auth_type}_{getattr(principal, 'key_id', '') or getattr(principal, 'user_id', '')}"
    except Exception:
        await websocket.close(code=1008, reason="auth_failed")
        return

    await manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action", "")
            if action == "subscribe":
                manager.set_filter(client_id, msg.get("filter", {}))
                await websocket.send_json({"status": "subscribed", "client_id": client_id})
            elif action == "ping":
                await websocket.send_json({"status": "pong"})
    except WebSocketDisconnect:
        await manager.disconnect(client_id)
    except Exception:
        await manager.disconnect(client_id)


@router.get("/v1/stream/sse")
async def stream_sse(request: Request, token: str = Query("")):
    if not token:
        return JSONResponse(status_code=401, content={"error": "missing_token"})
    try:
        from api.auth import AuthManager
        auth = AuthManager()
        principal = auth.verify_access_token(token)
        if principal is None:
            return JSONResponse(status_code=401, content={"error": "invalid_token"})
    except Exception:
        return JSONResponse(status_code=401, content={"error": "auth_failed"})

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            yield {"event": "heartbeat", "data": "ping"}
            await asyncio.sleep(30)

    return EventSourceResponse(event_generator())
