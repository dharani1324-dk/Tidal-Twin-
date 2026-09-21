"""Runtime sensor plugin architecture tests (feature #20).

Proves the plugin seam:
  - plugins register at runtime (instance OR class) and appear in /data-sources
  - SOURCE_ORDER governs the payload order; unknown plugins sort to the end
  - registering over an existing id hot-swaps the plugin
  - a plugin that raises at runtime yields an honest DEGRADED entry,
    never a crash
  - `load_dynamic` discovers a module that self-registers
  - the existing `data_sources()` contract (argo online/simulated) is intact
"""

import sys
import tempfile
import unittest
from pathlib import Path

from app.core.database import SessionLocal
from app.models.argo import ArgoProfile
from app.modules.ai.twin import plugins as P
from app.modules.ai.twin.sources import data_sources

_TMP = tempfile.TemporaryDirectory()


def tearDownModule():
    _TMP.cleanup()


class DummyBuoyPlugin(P.SensorPlugin):
    source_id = "dummy_buoy"
    name = "Dummy buoy array"
    kind = "observation"
    variables = ["Sea temperature"]

    def info(self, db, now):
        return {
            "id": self.source_id,
            "name": self.name,
            "kind": self.kind,
            "status": "online",
            "status_detail": "stub",
            "last_update": now.isoformat(),
            "variables": self.variables,
            "coverage_pct": 41.0,
            "note": "A runtime-registered test buoy.",
        }


class BrokenPlugin(P.SensorPlugin):
    source_id = "broken_sensor"
    name = "Broken sensor"
    kind = "observation"

    def info(self, db, now):
        raise RuntimeError("no uplink")


def _db():
    return SessionLocal()


def _plugin_dict(srcs, pid):
    return next(s for s in srcs["sources"] if s["id"] == pid)


class PluginRegistryTest(unittest.TestCase):
    def tearDown(self):
        for pid in ("dummy_buoy", "dummy_buoy2", "dummy_buoy_x", "broken_sensor"):
            P.deregister(pid)

    def test_register_instance_appears_alphabetized_as_unknown(self):
        P.register(DummyBuoyPlugin())
        payload = P.build_sources(_db())
        ids = [s["id"] for s in payload["sources"]]
        self.assertEqual(ids[:len(P.SOURCE_ORDER)], list(P.SOURCE_ORDER))
        self.assertIn("dummy_buoy", ids)
        self.assertGreater(ids.index("dummy_buoy"), ids.index("satellite"))
        self.assertEqual(len(payload["sources"]), len(P.SOURCE_ORDER) + 1)
        self.assertEqual(payload["health"]["total"], len(payload["sources"]))
        self.assertEqual(_plugin_dict(payload, "dummy_buoy")["coverage_pct"], 41.0)

    def test_register_class_and_hot_swap(self):
        P.register(DummyBuoyPlugin)  # class form
        first = _plugin_dict(P.build_sources(_db()), "dummy_buoy")
        self.assertEqual(first["name"], "Dummy buoy array")

        class Swapped(P.SensorPlugin):
            source_id = "dummy_buoy"
            name = "Dummy buoy array mk2"
            kind = "observation"

            def info(self, db, now):
                return {"id": self.source_id, "name": self.name, "kind": self.kind,
                        "status": "online", "status_detail": "swapped",
                        "last_update": now.isoformat(), "variables": [],
                        "coverage_pct": 0.0, "note": "replaced at runtime"}

        P.register(Swapped)
        second = _plugin_dict(P.build_sources(_db()), "dummy_buoy")
        self.assertEqual(second["name"], "Dummy buoy array mk2")
        self.assertEqual(len(P.build_sources(_db())["sources"]), len(P.SOURCE_ORDER) + 1)

    def test_broken_plugin_is_degraded_not_fatal(self):
        P.register(BrokenPlugin)
        payload = P.build_sources(_db())
        entry = _plugin_dict(payload, "broken_sensor")
        self.assertEqual(entry["status"], "offline")
        self.assertIn("plugin error", entry["status_detail"])
        self.assertIn("no uplink", entry["note"])
        self.assertIn("Broken sensor", payload["health"]["degraded"])
        # every other source still present
        self.assertEqual({s["id"] for s in payload["sources"]},
                         set(P.SOURCE_ORDER) | {"broken_sensor"})


class PluginDynamicLoadTest(unittest.TestCase):
    def tearDown(self):
        P.deregister("drift_mooring")
        for m in [m for m in sys.modules if m == "runtime_drifters"]:
            del sys.modules[m]

    def test_load_dynamic_discovers_self_registered_module(self):
        mod = ('import sys; from app.modules.ai.twin.plugins import register, SensorPlugin\n'
               'class DriftMooring(SensorPlugin):\n'
               '    source_id = "drift_mooring"\n'
               '    name = "Drift mooring"\n'
               '    kind = "observation"\n'
               '    def info(self, db, now):\n'
               '        return {"id": self.source_id, "name": self.name, "kind": self.kind,\n'
               '                "status": "online", "status_detail": "discovered",\n'
               '                "last_update": None, "variables": [],\n'
               '                "coverage_pct": 0.0, "note": "loaded at runtime"}\n'
               'register(DriftMooring)\n')
        pkg = Path(_TMP.name) / "runtime_drifters.py"
        pkg.write_text(mod, encoding="utf-8")
        sys_path = list(sys.path)
        sys.path.insert(0, _TMP.name)
        try:
            added = P.load_dynamic("runtime_drifters")
            self.assertEqual(added, ["drift_mooring"])
            entry = _plugin_dict(P.build_sources(_db()), "drift_mooring")
            self.assertEqual(entry["status"], "online")
            self.assertEqual(entry["status_detail"], "discovered")
        finally:
            sys.path[:] = sys_path


class DataSourcesContractTest(unittest.TestCase):
    def test_argo_online_simulated_contract(self):
        payload = data_sources(_db())
        argo = _plugin_dict(payload, "argo")
        self.assertIn(argo["status"], ("online", "simulated"))
        self.assertEqual(payload["health"]["online"], sum(
            1 for s in payload["sources"] if s["status"] == "online"))
        for src in payload["sources"]:
            for key in ("id", "name", "kind", "status", "status_detail",
                        "last_update", "variables", "coverage_pct", "note"):
                self.assertIn(key, src)


if __name__ == "__main__":
    import sys
    unittest.main()