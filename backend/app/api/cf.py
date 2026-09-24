"""
TidalTwin - OGC / CF metadata validation endpoints (feature #22)
==================================================================
  GET  /api/v1/cf/validate?path=data/model/file.nc   (server-local file)
  POST /api/v1/cf/validate                           (raw NetCDF bytes body)

Both run the same honest CF validator (`app.modules.ai.netcdf_validate`) and
return {valid, errors, warnings, passed, variables}. A file that does not
exist, or that a validator cannot parse, is reported as such - never an
"everything is fine" lie.
"""

import json
from pathlib import Path

from fastapi import APIRouter, Request, Response

from app.core.config import settings
from app.modules.ai import netcdf_validate as validator

router = APIRouter(prefix="/api/v1/cf", tags=["CF Validation"])


def _json(report: dict) -> Response:
    return Response(
        content=json.dumps(report, indent=2),
        media_type="application/json",
    )


@router.get("/validate", response_class=Response)
def validate_path(path: str):
    target = Path(path)
    if not target.is_absolute():
        target = settings.BASE_DIR / target
    try:
        exists = target.exists()
    except OSError:
        exists = False
    if not exists:
        return _json({
            "valid": False,
            "errors": [f"file not found: {target}"],
            "warnings": [],
            "passed": {},
            "variables": [],
        })
    return _json(validator.validate_netcdf(target))


@router.post("/validate", response_class=Response)
async def validate_body(request: Request):
    raw = await request.body()
    if not raw:
        return _json({
            "valid": False,
            "errors": ["empty upload"],
            "warnings": [],
            "passed": {},
            "variables": [],
        })
    return _json(validator.validate_netcdf(raw))