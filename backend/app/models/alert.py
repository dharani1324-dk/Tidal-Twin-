"""
OceanVerse AI - Weather/Anomaly Alert Model
===========================================
Represents an AI-generated warning about an ocean condition.
Examples: harmful algal bloom detected, unusual temperature spike,
potential storm surge, oil spill anomaly, unsafe fishing conditions.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class OceanAlert(Base):
    __tablename__ = "ocean_alerts"

    id = Column(Integer, primary_key=True, index=True)

    # Which location the alert is about
    location_id = Column(
        Integer, ForeignKey("ocean_locations.id"), nullable=False, index=True
    )

    # What kind of alert: e.g. "temperature_anomaly", "bloom", "storm_surge"
    alert_type = Column(String(100), nullable=False)

    # Severity: "low", "medium", "high", "critical"
    severity = Column(String(20), nullable=False, default="medium")

    # Human-readable description of what happened
    description = Column(String(2000), nullable=True)

    # Confidence score from the AI (0.0 to 1.0)
    confidence = Column(Float, nullable=True)

    # Coordinates of the event (helps display on the map)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Where the alert came from: "ai_anomaly", "ai_forecast", "system"
    source = Column(String(50), nullable=False, default="system")

    # Active vs resolved
    status = Column(String(20), nullable=False, default="active")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    location = relationship("OceanLocation", backref="alerts")

    def __repr__(self):
        return f"<OceanAlert id={self.id} type={self.alert_type} sev={self.severity}>"
