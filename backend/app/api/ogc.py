"""
TidalTwin - OGC WMS / WCS endpoints (feature #21)
====================================================
Two standards endpoints aliasing the OGC protocols on top of the REAL
ingested grids:

  GET /api/v1/ogc/wms?service=WMS&request=GetCapabilities
  GET /api/v1/ogc/wms?service=WMS&request=GetMap&layers=sst&bbox=65,5,95,25&width=512&height=512
  GET /api/v1/ogc/wcs?service=WCS&request=GetCapabilities
  GET /api/v1/ogc/wcs?service=WCS&request=GetCoverage&CoverageID=sst&subset=Lat(5,25)&subset=Long(65,95)

Empty / out-of-range requests return a standards ServiceException with a
plain-language reason - never a fabricated map.
"""

from fastapi import APIRouter, Query, Response

from app.core.database import SessionLocal
from app.modules.ai import ogc as ogc_mod

router = APIRouter(prefix="/api/v1/ogc", tags=["OGC WMS / WCS"])


def _db():
    return SessionLocal()


def _err(reason: str, code: str = "NoApplicableCode") -> Response:
    return Response(content=ogc_mod.service_exception(reason, code),
                    status_code=400, media_type="application/xml")


def _parse_bbox(raw: str | None):
    if not raw:
        return None
    parts = [p.strip() for p in str(raw).split(",")]
    if len(parts) != 4:
        return None
    try:
        return [float(p) for p in parts]
    except ValueError:
        return None


@router.get("/wms", response_class=Response)
def wms(
    service: str = Query(default="WMS"),
    request: str = Query(default="GetCapabilities"),
    layers: str | None = Query(default=None),
    bbox: str | None = Query(default=None),
    width: int | None = Query(default=None),
    height: int | None = Query(default=None),
    transparent: str | None = Query(default=None),
    format: str | None = Query(default=None),
    version: str | None = Query(default=None),
):
    if service.upper() != "WMS":
        return _err("service must be 'WMS'.")
    req = (request or "").lower()
    if req == "getcapabilities":
        db = _db()
        try:
            return Response(content=ogc_mod.wms_capabilities_xml(db),
                            media_type="application/xml")
        finally:
            db.close()

    if req == "getmap":
        if not layers:
            return _err("GetMap requires LAYERS=...")
        layer_names = [l.strip() for l in layers.split(",")]
        for ln in layer_names:
            if ln not in ogc_mod.COVERAGES:
                return _err(
                    f"Layer '{ln}' is not served. Known layers: {sorted(ogc_mod.COVERAGES)}.",
                    "LayerNotDefined")
        parsed = _parse_bbox(bbox)
        if parsed is None:
            return _err("GetMap requires a valid BBOX=minx,miny,maxx,maxy.")
        if width is None or height is None:
            return _err("GetMap requires WIDTH and HEIGHT.")
        if transparent is None:
            transparent = False
        elif transparent.lower() == "true":
            transparent = True
        elif transparent.lower() == "false":
            transparent = False
        else:
            return _err("TRANSPARENT must be TRUE or FALSE.")
        db = _db()
        try:
            png = ogc_mod.wms_get_map(db, layer_names, parsed, width, height,
                                      transparent=transparent)
        except ogc_mod.NoDataError as e:
            return _err(str(e))
        except KeyError as e:
            return _err(f"Unknown coverage: {e}", "LayerNotDefined")
        finally:
            db.close()
        return Response(content=png, media_type="image/png")

    return _err(f"Operation '{request}' not supported by this WMS.", "OperationNotSupported")


@router.get("/wcs", response_class=Response)
def wcs(
    service: str = Query(default="WCS"),
    request: str = Query(default="GetCapabilities"),
    coverage_id: str | None = Query(default=None, alias="CoverageID"),
    identifier: str | None = Query(default=None),
    subset: list[str] | None = Query(default=None),
    format: str | None = Query(default=None),
    version: str | None = Query(default=None),
):
    if service.upper() != "WCS":
        return _err("service must be 'WCS'.")
    req = (request or "").lower()
    if req == "getcapabilities":
        db = _db()
        try:
            return Response(content=ogc_mod.wcs_capabilities_xml(db),
                            media_type="application/xml")
        finally:
            db.close()

    if req == "getcoverage":
        cid = coverage_id or identifier
        if not cid:
            return _err("GetCoverage requires CoverageID=...")
        if cid not in ogc_mod.COVERAGES:
            return _err(
                f"Coverage '{cid}' is not served. Known coverage ids: {sorted(ogc_mod.COVERAGES)}.",
                "NoSuchCoverage")

        bbox = None
        if subset:
            lat_bounds = lon_bounds = None
            for s in subset:
                name = s.split("(", 1)[0].lower()
                inner = s.split("(", 1)[1].rstrip(")").strip()
                lo, hi = inner.split(",")
                lo, hi = float(lo.strip()), float(hi.strip())
                if name.startswith("lat"):
                    lat_bounds = (lo, hi)
                elif name.startswith("lon") or name.startswith("long"):
                    lon_bounds = (lo, hi)
            if lat_bounds and lon_bounds:
                bbox = [lon_bounds[0], lat_bounds[0], lon_bounds[1], lat_bounds[1]]

        if bbox is None:
            bbox = [-180.0, -90.0, 180.0, 90.0]

        if fmt := (format or "").lower():
            if "netcdf" not in fmt and "cdf" not in fmt:
                return _err(
                    f"Unsupported FORMAT '{format}'. This WCS serves application/x-netcdf.")

        db = _db()
        try:
            nc_bytes = ogc_mod.wcs_get_coverage_bytes(db, cid, *bbox)
        except ogc_mod.NoDataError as e:
            return _err(str(e))
        except KeyError as e:
            return _err(f"Unknown coverage: {e}", "NoSuchCoverage")
        finally:
            db.close()
        return Response(content=nc_bytes, media_type="application/x-netcdf")

    return _err(f"Operation '{request}' not supported by this WCS.", "OperationNotSupported")