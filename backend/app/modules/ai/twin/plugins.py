"""
TidalTwin - Runtime Sensor Plugin Architecture (feature #20)
================================================================
The twin grows new sensor types without touching `data_sources()`: every
source is a `SensorPlugin`, discovered/registered at runtime.

  - `SensorPlugin`: the contract every source implements. A plugin computes
    its own status / last-update / coverage / note from the REAL database
    (honest by construction - it never fabricates a live feed).
  - `register` / `PLUGINS`: the runtime registry.
  - `build_sources(db)`: assembles the /data-sources payload from whatever is
    registered. Ordering follows `SOURCE_ORDER`, anything else is appended.
  - A plugin that raises while running is reported as a DEGRADED entry
    ("plugin error: ...") instead of crashing the twin.

A new sensor type is added at runtime either by:
    from app.modules.ai.twin.plugins import register
    register(MyBuoyPlugin())          # instance
    register(MyBuoyPlugin)            # class (instantiated once)
or, for fully dynamic discovery, by loading a module path:
    load_dynamic("app.modules.ai.twin.drifters")
where that module constructs and `register()`s its plugin at import time.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from importlib import import_module

from sqlalchemy.orm import Session

# Fixed ordering used by the UI; anything not listed sorts to the end.
SOURCE_ORDER = [
    "open_meteo",
    "model_estimate",
    "argo",
    "gliders",
    "ersst",
    "ocean_model_grid",
    "physics_engine",
    "satellite",
]

# source_id -> plugin instance (insertion order preserved).
PLUGINS: dict[str, "SensorPlugin"] = {}


class SensorPlugin(ABC):
    """Base contract for a runtime data source."""

    source_id: str = ""
    name: str = ""
    kind: str = "observation"  # observation | model | derived
    variables: list[str] | None = None

    def __init__(self):
        if not self.source_id or not self.name:
            raise ValueError("SensorPlugin needs source_id and name")
        self.variables = self.variables or []

    @abstractmethod
    def info(self, db: Session, now: datetime) -> dict:
        """Return {id, name, kind, status, status_detail, last_update,
        variables, coverage_pct, note} computed from the REAL database."""

    def degraded(self, now: datetime, error: str) -> dict:
        """Honest fallback when a plugin fails at runtime."""
        return {
            "id": self.source_id,
            "name": self.name,
            "kind": self.kind,
            "status": "offline",
            "status_detail": "plugin error",
            "last_update": None,
            "variables": self.variables,
            "coverage_pct": 0.0,
            "note": f"Plugin '{self.source_id}' failed at runtime: {error}.",
        }


def register(plugin: "SensorPlugin | type[SensorPlugin]") -> SensorPlugin:
    """Register a plugin instance or class; registering the same id again
    replaces the previous plugin (hot-swap at runtime)."""
    if isinstance(plugin, type):
        plugin = plugin()
    if not isinstance(plugin, SensorPlugin):
        raise TypeError("register() expects a SensorPlugin instance or subclass")
    PLUGINS[plugin.source_id] = plugin
    return plugin


def deregister(source_id: str) -> None:
    PLUGINS.pop(source_id, None)


def load_dynamic(module_name: str) -> list[str]:
    """Import a plugin module (which calls register() itself) at runtime.
    Returns the source_ids it registered. A broken module yields an empty
    list and must be surfaced by the caller - it never kills the twin."""
    before = set(PLUGINS)
    import_module(module_name)
    return [pid for pid in PLUGINS if pid not in before]


def registered_ids() -> list[str]:
    return list(PLUGINS)


def _plugin_payload(plugin: SensorPlugin, db: Session, now: datetime) -> dict:
    try:
        info = plugin.info(db, now)
        info.setdefault("id", plugin.source_id)
        info.setdefault("name", plugin.name)
        info.setdefault("kind", plugin.kind)
        info.setdefault("variables", plugin.variables)
        return info
    except Exception as e:  # one bad plugin must not take the twin down
        return plugin.degraded(now, str(e))


def build_sources(db: Session) -> dict:
    """Assemble the /data-sources payload from the runtime registry."""
    now = datetime.now(timezone.utc)
    ordered: list[dict] = []
    for pid in SOURCE_ORDER:
        plugin = PLUGINS.get(pid)
        if plugin is not None:
            ordered.append(_plugin_payload(plugin, db, now))
    for pid, plugin in PLUGINS.items():  # plugin.not registered-listed -> append
        if pid not in SOURCE_ORDER:
            ordered.append(_plugin_payload(plugin, db, now))

    online = sum(1 for s in ordered if s["status"] == "online")
    return {
        "generated_at": now.isoformat(),
        "sources": ordered,
        "health": {
            "online": online,
            "total": len(ordered),
            "degraded": [s["name"] for s in ordered if s["status"] != "online"],
        },
    }