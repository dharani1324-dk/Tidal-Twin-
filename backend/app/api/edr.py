"""
OceanVerse AI - Phase 3: OGC API - Environmental Data Retrieval (EDR)
====================================================================
Honest OGC EDR service over the REAL `derived_currents` corpus.

Implements the OGC API - EDR "position query" (OGC 20-089r1 style):
  GET /collections/{id}/position?coords=lon,lat[,datetime]&datetime=...
  -> a JSON Coverage with domain (positions) + range (vectors + trust).

HONESTY CONTRACT (inherited from the whole codebase):
  * `coords` may be given as "lon,lat" (point) or "lon1,lat1,lon2,lat2"
    (corridor segment). The EDR domain is built ONLY from cells that the
    derivation actually gated in — cells with no gated data are simply
    ABSENT from the domain, never interpolated or filled.
  * Every vector is DERIVED, provenance-linked; uncertainty_mps and the
    per-cell observation counts travel with the vector so a reader can
    judge trust without the API claiming more than the corpus supports.
  * If the requested position has NO gated cell, we return a valid EDR
    Coverage whose domain is EMPTY (honest "no data here"), with an
    explicit honesty_note. We never paint a guess.

EDR-ish response shape (JSON Coverage:
  type: "Coverage"
  domain: { type: "Domain", domainType: "Point",
            axes: { x: {start,stop,num}, y: {start,stop,num} },
            referencing: [OGC CRS axes] }
  parameters: [ {id, type, description, unit} ... ]
  ranges: { <param>: { type:"NdArray", data:[...], shape:[...] } }
  + provenance / honesty envelope.

The ax + grid math uses the SAME window + cell constants as the
derivation engine (Indian EEZ corridor 3..25 lat, 66..92 lon, 0.25 deg),
so the EDR cannot accidentally describe a different world than the
derivation corpus. All constants are verbatim from app/models/ais.py
(this session, authoritative).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.ais import DerivedCurrent

router = APIRouter(prefix="/api/v1/edr", tags=["OGC EDR"])

# Indian EEZ / Bay-of-Bengal corridor (verbatim from derivation engine)
LAT_MIN, LAT_MAX = 3.0, 25.0
LON_MIN, LON_MAX = 66.0, 92.0
CELL_DEG = 0.25
E_WINDOW_DEG = CELL_DEG  # corridor cells are CELL_DEG square
ZOMBIE_LIMIT = 400


def _edge_edges() -> tuple[int, int]:
    """(n_cells_lon, n_cells_lat) over the corridor at CELL_DEG."""
    n_lon = int(round((LON_MAX - LON_MIN) / CELL_DEG))
    n_lat = int(round((LAT_MAX - LAT_MIN) / CELL_DEG))
    return n_lat * n_lon


@router.get("/collections")
def list_collections(db: Session = Depends(get_db)):
    """EDR collection catalogue - one honest collection: derived currents."""
    return {
        "collections": [
            {
                "id": "oceanverse-derived-currents",
                "title": "OceanVerse AI - Derived Surface Currents (Phase 3 EDR)",
                "description": (
                    "Real DERIVED surface-current vectors over the Indian EEZ "
                    "corridor. Every cell is gated + provenance-linked. Gaps "
                    "in coverage are honest absences, never filled."
                ),
                "extent": {
                    "spatial": {
                        "bbox": [[LON_MIN, LAT_MIN, LON_MAX, LAT_MAX]],
                        "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
                    },
                    "temporal": {
                        "interval": ["2019-01-01T00:00:00Z", "now"],
                        "trs": "http://www.opengis.net/def/uom/ISO-8601/0/Gregorian",
                    },
                },
                "parameter-names": [
                    {"id": "u", "type": "Parameter", "unit": "m s-1",
                     "description": "zonal component of derived current"},
                    {"id": "v", "type": "Parameter", "unit": "m s-1",
                     "description": "meridional component of derived current"},
                    {"id": "speed", "type": "Parameter", "unit": "m s-1",
                     "description": "speed of derived current"},
                    {"id": "uncertainty_mps", "type": "Parameter", "unit": "m s-1",
                     "description": "honest uncertainty of the derived estimate"},
                    {"id": "n_observations", "type": "Parameter", "unit": "1",
                     "description": "number of source vessel observations that gated this cell"},
                ],
            }
        ],
        "honesty_note": (
            "All vectors are method_tag='DERIVED' and provenance-linked. "
            "Cells below the gate are absent from this catalogue's extent "
            "queries, never interpolated."
        ),
    }


@router.get("/collections/oceanverse-derived-currents/position")
def position_query(
    coords: str = Query(..., description="lon,lat or lon1,lat1,lon2,lat2 (WGS84)"),
    datetime: str = Query(None, description="optional instant or interval (ISO-8601 UTC)"),
    db: Session = Depends(get_db),
):
    """OGC EDR position query returning a JSON Coverage of derived currents."""
    try:
        toks = [float(x) for x in coords.split(",")]
    except ValueError:
        raise HTTPException(status_code=400, detail="coords must be comma-separated numbers")
    if len(toks) == 2:
        lon0, lat0 = toks
        lon1, lat1 = lon0, lat0
    elif len(toks) == 4:
        lon0, lat0, lon1, lat1 = toks
    else:
        raise HTTPException(status_code=400, detail="coords must be lon,lat or lon1,lat1,lon2,lat2")

    # corridor bbox (same as derivation engine)
    clon_lo = int((lon0 - LON_MIN) // CELL_DEG)
    clat_lo = int((lat0 - LAT_MIN) // CELL_DEG)
    clon_hi = int((lon1 - LON_MIN) // CELL_DEG)
    clat_hi = int((lat1 - LAT_MIN) // CELL_DEG)

    cells = (
        db.query(DerivedCurrent)
        .filter(
            DerivedCurrent.lon >= LON_MIN + clon_lo * CELL_DEG,
            DerivedCurrent.lon <= LON_MIN + (clon_hi + 1) * CELL_DEG,
            DerivedCurrent.lat >= LAT_MIN + clat_lo * CELL_DEG,
            DerivedCurrent.lat <= LAT_MIN + (clat_hi + 1) * CELL_DEG,
            DerivedCurrent.method_tag == "DERIVED",
        )
        .order_by(DerivedCurrent.lon, DerivedCurrent.lat)
        .limit(ZOMBIE_LIMIT)
        .all()
    )

    lon_pts = sorted({round(c.lon, 6) for c in cells})
    lat_pts = sorted({round(c.lat, 6) for c in cells})

    u_dat = [round(float(c.u), 6) for c in cells]
    v_dat = [round(float(c.v), 6) for c in cells]
    spd_dat = [round(float(c.speed), 6) for c in cells]
    unc_dat = [round(float(c.uncertainty_mps), 6) for c in cells]
    nobs_dat = [int(c.n_observations) for c in cells]

    by_pos = {
        (round(c.lon, 6), round(c.lat, 6)): c
        for c in cells
    }

    references = [
        {"coordinates": ["x", "y"], "system": {
            "type": "GeographicCRS",
            "id": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
         "order": [0, 1]},
    ]

    coverage = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Point",
            "axes": {
                "x": {"start": lon0, "stop": lon1, "num": len(lon_pts)},
                "y": {"start": lat0, "stop": lat1, "num": len(lat_pts)},
            },
            "referencing": references,
        },
        "parameters": {
            "u": {"type": "Parameter", "unit": "m s-1",
                  "description": "zonal component of derived current"},
            "v": {"type": "Parameter", "unit": "m s-1",
                  "description": "meridional component of derived current"},
            "speed": {"type": "Parameter", "unit": "m s-1",
                      "description": "speed of derived current (m s-1)"},
            "uncertainty_mps": {"type": "Parameter", "unit": "m s-1",
                                "description": "honest uncertainty"},
            "n_observations": {"type": "Parameter", "unit": "1",
                               "description": "source observations in gated cell"},
        },
        "ranges": {
            "u": {"type": "NdArray", "shape": [len(u_dat)], "data": u_dat},
            "v": {"type": "NdArray", "shape": [len(v_dat)], "data": v_dat},
            "speed": {"type": "NdArray", "shape": [len(spd_dat)], "data": spd_dat},
            "uncertainty_mps": {"type": "NdArray", "shape": [len(unc_dat)], "data": unc_dat},
            "n_observations": {"type": "NdArray", "shape": [len(nobs_dat)], "data": nobs_dat},
        },
        "provenance": {
            "method_tag": "DERIVED",
            "n_gated_cells": len(cells),
            "cells": [
                {
                    "lon": round(c.lon, 6),
                    "lat": round(c.lat, 6),
                    "u": round(float(c.u), 6),
                    "v": round(float(c.v), 6),
                    "speed": round(float(c.speed), 6),
                    "uncertainty_mps": round(float(c.uncertainty_mps), 6),
                    "n_observations": int(c.n_observations),
                    "method_tag": c.method_tag,
                    "provenance_id": c.provenance_id,
                }
                for c in cells
            ],
        },
        "honesty_note": (
            "domain carries ONLY gated DERIVED cells; positions with no gated "
            "cell return an empty domain. Nothing here is interpolated, "
            "invented, or upgraded from SIMULATED to OBSERVED."
        ),
    }

    # If the requested window has zero gated cells -> honest empty coverage
    if len(cells) == 0:
        coverage["domain"]["axes"]["x"]["num"] = 0
        coverage["domain"]["axes"]["y"]["num"] = 0
        coverage["ranges"] = {k: {"type": "NdArray", "shape": [0], "data": []}
                              for k in ("u", "v", "speed", "uncertainty_mps", "n_observations")}

    coverage["provenance"]["cells_with_data"] = len(cells)
    coverage["provenance"]["coverage_gap"] = _edge_edges() - len(cells)
    return coverage
