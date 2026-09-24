"""
TidalTwin - OGC WMS / WCS services (feature #21)
====================================================
Standards-compliant publishing of the REAL ingested grids so any OGC client
(GIS tools, QGIS, MapServer) can pull the twin's data:

  - WMS   1.3.0  `GetCapabilities`, `GetMap` -> image/png (nearest-neighbour
                resample of the real grid over the requested BBOX)
  - WCS   2.0.1  `GetCapabilities`, `GetCoverage` -> application/x-netcdf
                (CF-annotated lat/lon coverage of the real grid)

Honesty rules (shared with every other real-data path):
  - a layer/coverage is only served if the real grid is ingested;
  - cells farther than the product's honest search range are transparent
    (WMS) / NaN (WCS) - never interpolated into existence;
  - empty or unreachable data responds with a standards `ServiceException`
    and a plain-language reason.

Grids publishable today: sst (NOAA ERSST v5), chlor_a (CoastWatch VIIRS·Himawari).
"""

import io
import math

import numpy as np
import xarray as xr
from PIL import Image
from scipy.spatial import cKDTree

from app.modules.ai.realdata import SOURCES, latest_grid

MAX_TILE = 1024

# coverage id -> metadata (variable name per the realdata registry).
COVERAGES = {
    "sst": {
        "variable": "sst",
        "title": "Sea surface temperature (NOAA ERSST v5 real grid)",
        "long_name": "Sea surface temperature",
        "standard_name": "sea_surface_temperature",
        "units": "degC",
    },
    "chlor_a": {
        "variable": "chlor_a",
        "title": "Chlorophyll-a (CoastWatch VIIRS·Himawari real grid)",
        "long_name": "Chlorophyll a",
        "standard_name": "mass_concentration_of_chlorophyll_a_in_sea_water",
        "units": "mg m-3",
    },
}

# colour stops for the value -> colour ramp (divergent blue-red).
_STOPS = [0.0, 0.25, 0.5, 0.75, 1.0]
_COLORS = [
    (0, 53, 179),
    (0, 180, 255),
    (48, 222, 111),
    (255, 204, 71),
    (232, 24, 24),
]


class NoDataError(Exception):
    """Raised when the requested coverage has no honest real cells."""


def coverage_meta(coverage_id: str) -> dict:
    if coverage_id not in COVERAGES:
        raise KeyError(f"Unknown OGC coverage '{coverage_id}'. Known: {sorted(COVERAGES)}")
    meta = dict(COVERAGES[coverage_id])
    info = SOURCES[meta["variable"]]
    meta["source"] = info["label"]
    return meta


def grid_cells(db, coverage_id: str, lon0: float, lat0: float,
               lon1: float, lat1: float, width: int, height: int,
               max_deg: float | None = None) -> tuple:
    """Nearest-neighbour resample of the REAL grid to a WIDTH x HEIGHT raster
    inside [lon0,lat0]-[lon1,lat1]. Returns (grid2d, vmin, vmax); unreachable
    cells are NaN. Raises NoDataError (honest) when the coverage is absent or
    every cell is out of the honest search range."""
    meta = coverage_meta(coverage_id)
    info = SOURCES[meta["variable"]]
    limit = info["default_max_deg"] if max_deg is None else max_deg

    grid = latest_grid(db, meta["variable"])
    if not grid.get("available"):
        raise NoDataError(info["reason_no_data"])
    samples = grid.get("samples") or []
    if not samples:
        raise NoDataError(f"Latest month has no {info['short']} cells.")

    lats = np.array([s[0] for s in samples], dtype=float)
    lons = np.array([s[1] for s in samples], dtype=float)
    vals = np.array([s[2] for s in samples], dtype=float)

    w = max(int(width), 2)
    h = max(int(height), 2)
    cosf = math.cos(math.radians((lat0 + lat1) / 2.0))
    # scale longitude so euclidean KD-tree distances approximate great-circle deg.
    tree = cKDTree(np.column_stack([lats, lons * cosf]))
    xs = np.linspace(lon0, lon1, w) if w > 1 else np.array([(lon0 + lon1) / 2.0])
    ys = np.linspace(lat1, lat0, h) if h > 1 else np.array([(lat0 + lat1) / 2.0])
    xx, yy = np.meshgrid(xs, ys)
    dist, idx = tree.query(np.column_stack([yy.ravel(), (xx * cosf).ravel()]))

    grid2 = vals[idx].reshape(h, w).astype(float)
    grid2 = grid2.ravel()
    grid2[dist > limit] = np.nan
    grid2 = grid2.reshape(h, w)

    valid = grid2[~np.isnan(grid2)]
    if valid.size == 0:
        raise NoDataError(
            f"No real {info['short']} cell within {limit:g}° of the requested bounds.")
    return grid2, float(np.nanmin(valid)), float(np.nanmax(valid))


def value_color(v, vmin, vmax):
    """Map a value onto the blue->red ramp. vmin==vmax -> mid ramp."""
    rng = (vmax - vmin) or 1.0
    t = (v - vmin) / rng
    for i, stop in enumerate(_STOPS[:-1]):
        if t <= stop:
            return _COLORS[0]
    for i in range(len(_STOPS) - 1):
        lo, hi = _STOPS[i], _STOPS[i + 1]
        if lo <= t <= hi:
            f = 0.0 if hi == lo else (t - lo) / (hi - lo)
            ca, cb = _COLORS[i], _COLORS[i + 1]
            return tuple(int(round(ca[k] + (cb[k] - ca[k]) * f)) for k in range(3))
    return _COLORS[-1]


def render_png(grid, vmin, vmax, transparent: bool = True) -> bytes:
    """RGBA PNG of the raster. NaN cells are transparent (or pale grey when
    `transparent` is false) - they are honest "no cell here" pixels."""
    h, w = grid.shape
    flat = grid.ravel().astype(float)
    valid = ~np.isnan(flat)

    t = np.zeros_like(flat)
    rng = (vmax - vmin) or 1.0
    t[valid] = (flat[valid] - vmin) / rng
    t = np.clip(t, 0.0, 1.0)

    r = np.interp(t, _STOPS, [c[0] for c in _COLORS])
    g = np.interp(t, _STOPS, [c[1] for c in _COLORS])
    b = np.interp(t, _STOPS, [c[2] for c in _COLORS])

    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[:, :, 0] = r.reshape(h, w)
    out[:, :, 1] = g.reshape(h, w)
    out[:, :, 2] = b.reshape(h, w)
    out[:, :, 3] = 255
    if transparent:
        alpha = np.zeros((h, w), dtype=np.uint8)
        alpha[valid.reshape(h, w)] = 255
        out[:, :, 3] = alpha
    else:
        out[~valid.reshape(h, w), 0:3] = 200
        out[~valid.reshape(h, w), 3] = 255

    buf = io.BytesIO()
    Image.fromarray(out, mode="RGBA").save(buf, format="PNG")
    return buf.getvalue()


def service_exception(message: str, code: str = "NoApplicableCode") -> bytes:
    """OGC-style service exception XML with a plain-language reason."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ServiceExceptionReport xmlns="http://www.opengis.net/ogc" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="http://www.opengis.net/ogc" version="1.3.0">\n'
        f'  <ServiceException code="{code}">{message}</ServiceException>\n'
        '</ServiceExceptionReport>\n'
    )
    return xml.encode("utf-8")


# ---------------------------------------------------------------------------
# WMS 1.3.0
# ---------------------------------------------------------------------------


def wms_capabilities_xml(db) -> bytes:
    layers = ""
    for cid in COVERAGES:
        meta = coverage_meta(cid)
        info = SOURCES[meta["variable"]]
        layers += (
            f'<Layer queryable="1"><Name>{cid}</Name>'
            f'<Title>{meta["title"]}</Title>'
            f'<Abstract>{info["label"]}</Abstract>'
            '<CRS>EPSG:4326</CRS>'
            '<BoundingBox CRS="EPSG:4326" minx="-180" miny="-90" maxx="180" maxy="90"/>'
            '</Layer>'
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<WMS_Capabilities version="1.3.0" '
        'xmlns="http://www.opengis.net/wms" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
        '<Service>'
        '<Name>WMS</Name>'
        '<Title>TidalTwin Ocean Digital Twin</Title>'
        '<Abstract>Real ingested ocean grids (WMS 1.3.0). Data is real, not simulated.</Abstract>'
        '</Service>'
        '<Capability>'
        '<Request>'
        '<GetCapabilities>'
        '<Format>text/xml</Format>'
        '<DCPType><HTTP><Get><OnlineResource xlink:href="/api/v1/ogc/wms"/></Get></HTTP></DCPType>'
        '</GetCapabilities>'
        '<GetMap>'
        '<Format>image/png</Format>'
        '<Format>image/png; mode=32bit</Format>'
        '<DCPType><HTTP><Get><OnlineResource xlink:href="/api/v1/ogc/wms"/></Get></HTTP></DCPType>'
        '</GetMap>'
        '</Request>'
        '<Exception><Format>application/vnd.ogc.se_xml</Format></Exception>'
        '<Layer><Title>TidalTwin</Title><CRS>EPSG:4326</CRS>'
        + layers +
        '</Layer>'
        '</Capability>'
        '</WMS_Capabilities>\n'
    )
    return xml.encode("utf-8")


def wms_get_map(db, layers, bbox, width, height, transparent: bool = True,
                max_deg: float | None = None) -> bytes:
    """Render a real grid tile. Raises NoDataError for honest emptiness."""
    lon0, lat0, lon1, lat1 = bbox
    if width > MAX_TILE or height > MAX_TILE:
        raise NoDataError(f"Requested tile {width}x{height} exceeds the {MAX_TILE}px limit.")
    if width < 1 or height < 1:
        raise NoDataError("Tile width/height must be >= 1px.")
    grid, vmin, vmax = grid_cells(db, layers[0], lon0, lat0, lon1, lat1,
                                  width, height, max_deg)
    return render_png(grid, vmin, vmax, transparent=transparent)


# ---------------------------------------------------------------------------
# WCS 2.0.1
# ---------------------------------------------------------------------------


def wcs_capabilities_xml(db) -> bytes:
    contents = ""
    for cid in COVERAGES:
        meta = coverage_meta(cid)
        contents += (
            f'<wcs:CoverageSummary>'
            f'<wcs:CoverageId>{cid}</wcs:CoverageId>'
            f'<wcs:CoverageSubtype>RectifiedGridCoverage</wcs:CoverageSubtype>'
            f'<wcs:CoverageSubtypeType codeSpace="http://www.opengis.net/def/type/IS_Coverage">'
            f'http://www.opengis.net/def/type/IS_Coverage</wcs:CoverageSubtypeType>'
            f'<ows:Title>{meta["title"]}</ows:Title>'
            f'<ows:Abstract>{meta["source"]}</ows:Abstract>'
            '</wcs:CoverageSummary>'
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<wcs:Capabilities xmlns:wcs="http://www.opengis.net/wcs/2.0" '
        'xmlns:ows="http://www.opengis.net/ows/2.0" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" version="2.0.1">'
        '<ows:ServiceIdentification>'
        '<ows:Title>TidalTwin Ocean Digital Twin</ows:Title>'
        '<ows:Abstract>Real ingested ocean coverages (WCS 2.0.1) as CF NetCDF.</ows:Abstract>'
        '<ows:ServiceType>WCS</ows:ServiceType>'
        '<ows:ServiceTypeVersion>2.0.1</ows:ServiceTypeVersion>'
        '</ows:ServiceIdentification>'
        '<wcs:ServiceMetadata>'
        '<wcs:formatSupported>application/x-netcdf</wcs:formatSupported>'
        '</wcs:ServiceMetadata>'
        '<wcs:Contents>' + contents + '</wcs:Contents>'
        '</wcs:Capabilities>\n'
    )
    return xml.encode("utf-8")


def wcs_get_coverage_bytes(db, coverage_id: str, lon0, lat0, lon1, lat1,
                           width: int = 180, height: int = 90,
                           max_deg: float | None = None) -> bytes:
    """CF-annotated netCDF coverage. Raises NoDataError for honest emptiness."""
    if width > MAX_TILE or height > MAX_TILE:
        raise NoDataError(f"Requested coverage {width}x{height} exceeds the {MAX_TILE}px limit.")
    meta = coverage_meta(coverage_id)
    grid, vmin, vmax = grid_cells(db, coverage_id, lon0, lat0, lon1, lat1,
                                  width, height, max_deg)
    lats = np.linspace(lat1, lat0, int(height))
    lons = np.linspace(lon0, lon1, int(width))
    var = meta["variable"]
    ds = xr.Dataset(
        {var: (("lat", "lon"), grid)},
        coords={"lat": lats, "lon": lons},
        attrs={"Conventions": "CF-1.8", "source": meta["source"]},
    )
    ds[var].attrs = {
        "long_name": meta["long_name"],
        "standard_name": meta["standard_name"],
        "units": meta["units"],
        "grid_mapping": "crs",
        "cell_methods": "time: mean",
    }
    ds["crs"] = xr.DataArray(0, attrs={
        "grid_mapping_name": "latitude_longitude",
        "longitude_of_prime_meridian": 0.0,
        "semi_major_axis": 6378137.0,
        "inverse_flattening": 298.257223563,
    })
    return ds.to_netcdf()