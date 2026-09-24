"""TidalTwin - Live broadcast (WebSocket push)"""

import asyncio
from datetime import datetime, timezone

from fastapi import WebSocket

from app.core.database import SessionLocal
from app.models.alert import OceanAlert
from app.modules.ai.safety.advisory import model_trust, safety_advisory, storm_track


class LiveManager:
    """Tracks connected clients and fans a message out to every one."""

    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)

    async def broadcast(self, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.discard(ws)


manager = LiveManager()


def live_snapshot() -> dict:
    """A compact JSON snapshot pushed every few seconds over the socket."""
    db = SessionLocal()
    try:
        advisories = safety_advisory(db)
        danger = [a for a in advisories if a["status"] == "danger"]
        caution = [a for a in advisories if a["status"] == "caution"]

        trust = model_trust(db)["regions"]
        trust_avg = (
            round(sum(t["trust_score"] for t in trust) / len(trust)) if trust else 0
        )

        alerts_q = (
            db.query(OceanAlert)
            .filter(OceanAlert.status == "active")
            .order_by(OceanAlert.created_at.desc())
            .limit(6)
            .all()
        )
        alerts = [
            {
                "id": a.id,
                "location": a.location.name if a.location else None,
                "severity": a.severity,
                "type": a.alert_type,
                "confidence": round(a.confidence, 2) if a.confidence is not None else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in alerts_q
        ]

        track = storm_track()
        points = track["points"]
        # Advance the "eye" roughly one point every 5 minutes.
        idx = int(datetime.now(timezone.utc).timestamp() // 300) % (len(points) - 1)
        eye = points[idx]

        return {
            "type": "live",
            "t": datetime.now(timezone.utc).isoformat(),
            "danger_zones": len(danger),
            "caution_zones": len(caution),
            "top_risk": [
                {
                    "location": a["location"],
                    "risk_index": a["risk_index"],
                    "status": a["status"],
                }
                for a in advisories[:3]
            ],
            "trust_avg": trust_avg,
            "alerts": alerts,
            "storm": {
                "name": track["name"],
                "lat": eye["lat"],
                "lon": eye["lon"],
                "wind_kmh": eye["wind_kmh"],
                "headline": track["headline"],
            },
        }
    finally:
        db.close()


async def broadcast_loop(interval: float = 12.0) -> None:
    """Periodically push a fresh snapshot to every connected client."""
    while True:
        await asyncio.sleep(interval)
        try:
            snapshot = await asyncio.to_thread(live_snapshot)
            await manager.broadcast(snapshot)
        except Exception:
            continue