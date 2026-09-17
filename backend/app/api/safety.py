"""TidalTwin - Safety & Advisory API"""

import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.ai.safety.advisory import (
    merged_timeseries,
    model_trust,
    safety_advisory,
    storm_track,
)
from app.modules.ai.safety.live import live_snapshot, manager

router = APIRouter(prefix="/api/v1/safety", tags=["Safety & Advisory"])


@router.get("/advisory")
def advisory(db: Session = Depends(get_db)) -> dict:
    return {
        "regions": safety_advisory(db),
    }


@router.get("/storm")
def storm() -> dict:
    return storm_track()


@router.get("/trust")
def trust(db: Session = Depends(get_db)) -> dict:
    return model_trust(db)


@router.get("/timeseries")
def timeseries(db: Session = Depends(get_db)) -> dict:
    from datetime import datetime, timezone

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regions": merged_timeseries(db),
    }


@router.websocket("/ws/live")
async def live_feed(websocket: WebSocket) -> None:
    """Live push channel for the command center (advisory + storm + alerts)."""
    await manager.connect(websocket)
    try:
        # Send an immediate snapshot, then keep the socket alive.
        await websocket.send_json(await asyncio.to_thread(live_snapshot))
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)