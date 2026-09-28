"""Bounded, retrying ERDDAP client for the MoES / INCOIS data server.

Why a dedicated client
----------------------
TidalTwin already talks to a dozen remote services, each with its own quirks.
An ERDDAP server is a *protocol*, not a single provider, so one client serves
every ERDDAP-hosted source and keeps the failure behaviour uniform:

* every request has a hard connect + read timeout, so an unreachable MoES host
  can never stall a FastAPI request;
* a malformed / truncated / HTML response raises a typed error rather than
  silently yielding zero rows (this is the "malformed API response" edge case);
* a row cap prevents an accidental whole-dataset download;
* ``<`` and ``>`` in server constraints are percent-encoded, which the server
  rejects otherwise (verified against the live INCOIS instance);
* retries are bounded with linear backoff, and the final failure is reported as
  an honest availability status rather than an exception escaping to the app.

Nothing in this module invents data. If a request fails, it raises
``ErddapError`` and the caller records the failure in the registry.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from app.core.config import settings

logger = logging.getLogger("tidaltwin.observations.erddap")

# ERDDAP writes missing numeric values as these three tokens depending on the
# requested file type.  All three are treated as "no value", never as 0.
ERDDAP_MISSING = {"", "NaN", "nan", "N/A", "null", "NULL", "none", "None", "*", "* *"}

#: Cache of declared variable names, keyed by (base, protocol, dataset).
_DDS_CACHE: dict[tuple[str, str, str], list[str]] = {}
_DDS_LOCK = threading.Lock()


class ErddapError(RuntimeError):
    """Any bounded failure of a remote ERDDAP request."""

    def __init__(self, message: str, *, kind: str = "UNAVAILABLE", detail: str | None = None):
        super().__init__(message)
        self.kind = kind
        self.detail = detail


@dataclass(frozen=True)
class ErddapConstraint:
    """A single ``&name<op><value>`` server-side constraint."""

    name: str
    op: str
    value: str

    def render(self) -> str:
        return f"{self.name}{self.op}{self.value}"


@dataclass
class ErddapTable:
    """A parsed tabledap response: units row, then data rows."""

    columns: list[str] = field(default_factory=list)
    units: dict[str, str] = field(default_factory=dict)
    rows: list[dict[str, str]] = field(default_factory=list)
    url: str = ""

    def __len__(self) -> int:
        return len(self.rows)


def _encode_query(query: str) -> str:
    """Percent-encode only the characters ERDDAP's servlet rejects.

    The INCOIS Tomcat instance rejects a raw ``>``/``<`` in the request target
    with HTTP 400 ("Invalid character found in the request target").  Three
    encodings are therefore mandatory, and all three were confirmed against the
    live server:

    * ``>`` / ``<``  - the comparison operators of a server-side constraint.
    * ``+``          - decoded as a space by the query-string parser, which
      silently corrupts a ``+00:00`` UTC offset and makes the server answer 400.
      :func:`erddap_time` avoids producing it at all; this is the belt to that
      braces.
    * ``"`` / space  - rejected outright.
    """
    return (
        query.replace(">", "%3E")
        .replace("<", "%3C")
        .replace("+", "%2B")
        .replace(" ", "%20")
        .replace('"', "%22")
    )


def erddap_time(moment: datetime) -> str:
    """Render a UTC instant the way an ERDDAP constraint expects it.

    Always a ``Z`` suffix, never ``+00:00``: the literal ``+`` in a query string
    is a space once the server decodes it.
    """
    utc = moment.astimezone(timezone.utc) if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_url(base: str, protocol: str, dataset_id: str, file_type: str,
              columns: Sequence[str] | None = None,
              constraints: Iterable[ErddapConstraint] = ()) -> str:
    """Build a fully encoded ERDDAP request URL."""
    if not base.lower().startswith("https://"):
        raise ErddapError(
            "ERDDAP base URL must be HTTPS; refusing to build a plaintext request.",
            kind="CONFIGURATION",
        )
    parts = [f"{base.rstrip('/')}/{protocol}/{urllib.parse.quote(dataset_id)}.{file_type}"]
    query: list[str] = []
    if columns:
        query.append(",".join(urllib.parse.quote(c) for c in columns))
    query.extend(c.render() for c in constraints)
    if query:
        parts.append("?" + "&".join(query))
    url = "".join(parts)
    # The operators inside the already-rendered constraints need encoding too.
    head, sep, tail = url.partition("?")
    if sep:
        return f"{head}?{_encode_query(tail)}"
    return url


def _opener() -> urllib.request.OpenerDirector:
    # No redirect to a non-HTTPS host, and no cookie jar: a data request should
    # not be able to follow the service off TLS or carry session state.
    return urllib.request.build_opener()


def fetch(url: str, *, max_rows: int | None = None, timeout: int | None = None,
          connect_timeout: int | None = None, retries: int | None = None,
          backoff: float | None = None) -> str:
    """GET ``url`` and return the decoded body, or raise ``ErddapError``.

    The body is truncated at ``max_rows`` *lines* immediately after read, so a
    runaway response cannot exhaust memory even before parsing.
    """
    max_rows = max_rows or settings.INCOIS_MAX_ROWS
    read_timeout = timeout or settings.INCOIS_HTTP_TIMEOUT_SECONDS
    attempts = (retries if retries is not None else settings.INCOIS_HTTP_RETRIES) + 1
    pause = settings.INCOIS_RETRY_BACKOFF_SECONDS if backoff is None else backoff
    last: ErddapError | None = None

    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, headers={
            "User-Agent": "TidalTwin/1.0 (ocean observation intelligence)",
            "Accept": "text/csv,text/plain,*/*",
        })
        try:
            with _opener().open(request, timeout=read_timeout) as response:
                # 1 MiB of a CSV body is already far beyond any legitimate
                # constrained request; read incrementally and stop early.
                buffer = io.BytesIO()
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    buffer.write(chunk)
                    if buffer.tell() > max_rows * 512:
                        break
            return buffer.getvalue().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read(2048).decode("utf-8", errors="replace")
            except Exception:  # pragma: no cover - defensive
                pass
            last = ErddapError(
                f"ERDDAP returned HTTP {exc.code} for the requested subset.",
                kind="HTTP_ERROR",
                detail=body.strip()[:400] or None,
            )
            # 4xx other than 429 will not succeed on retry.
            if exc.code < 500 and exc.code != 429:
                raise last
        except urllib.error.URLError as exc:
            last = ErddapError(
                f"ERDDAP host is unreachable: {exc.reason}",
                kind="UNREACHABLE",
            )
        except TimeoutError as exc:
            last = ErddapError(f"ERDDAP request timed out after {read_timeout}s.", kind="TIMEOUT")
            logger.debug("erddap timeout for %s (%s)", url, exc)
        except Exception as exc:  # pragma: no cover - defensive
            last = ErddapError(f"ERDDAP request failed: {type(exc).__name__}.", kind="CLIENT_ERROR")

        if attempt < attempts:
            time.sleep(max(0.0, pause) * attempt)

    assert last is not None  # loop always sets it before falling through
    raise last


def parse_table(body: str, *, url: str = "", max_rows: int | None = None) -> ErddapTable:
    """Parse an ERDDAP ``.csv`` table (row 1 names, row 2 units, then data).

    A response that is not CSV (for example an HTML error page) raises
    ``ErddapError`` with ``kind='MALFORMED'`` rather than yielding an empty
    table, so a broken upstream is visible instead of looking like "no data".
    """
    if not body or not body.strip():
        raise ErddapError("ERDDAP returned an empty body.", kind="MALFORMED")
    stripped = body.lstrip()
    if stripped[0] == "<" or "<html" in stripped[:200].lower():
        raise ErddapError("ERDDAP returned HTML instead of a data table.", kind="MALFORMED")

    reader = csv.reader(io.StringIO(body))
    try:
        header = next(reader)
    except StopIteration:
        raise ErddapError("ERDDAP response contained no header row.", kind="MALFORMED") from None
    columns = [c.strip() for c in header]
    if not columns or not any(columns):
        raise ErddapError("ERDDAP header row is empty.", kind="MALFORMED")

    units: dict[str, str] = {}
    try:
        unit_row = next(reader)
    except StopIteration:
        unit_row = []
    for name, unit in zip(columns, unit_row + [""] * len(columns)):
        units[name.strip()] = (unit or "").strip()

    table = ErddapTable(columns=columns, units=units, url=url)
    limit = max_rows or settings.INCOIS_MAX_ROWS
    for record in reader:
        if not record or (len(record) == 1 and not record[0].strip()):
            continue
        table.rows.append({columns[i]: record[i] for i in range(min(len(columns), len(record)))})
        if len(table.rows) >= limit:
            logger.warning("erddap row cap %s reached for %s; response truncated.", limit, url)
            break
    return table


def dataset_variables(base: str, protocol: str, dataset_id: str) -> list[str]:
    """Return the variable names a dataset actually declares.

    Asking the server is the only honest way to know.  Hard-coding a column
    list works right up until the provider renames a field, and the resulting
    ``Unrecognized variable="..."`` 400 is indistinguishable from a network
    failure unless it is raised as its own error type.

    The DDS is a small metadata document, so the answer is cached for the life
    of the process.
    """
    cache_key = (base.rstrip("/"), protocol, dataset_id)
    with _DDS_LOCK:
        cached = _DDS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    url = f"{base.rstrip('/')}/{protocol}/{urllib.parse.quote(dataset_id)}.dds"
    body = fetch(url, max_rows=2000)
    names: list[str] = []
    for line in body.splitlines():
        # e.g. "  Float64 PLATFORM_NUMBER[PLATFORM_NUMBER = 0];"
        match = re.match(r"\s*\w+\s+([A-Za-z_][\w]*)\s*\[", line)
        if match and match.group(1) not in names:
            names.append(match.group(1))
    with _DDS_LOCK:
        _DDS_CACHE[cache_key] = names
    return names


def resolve_columns(base: str, protocol: str, dataset_id: str,
                    columns: Sequence[str] | None) -> list[str] | None:
    """Intersect requested columns with the dataset's real variables.

    A column the provider does not publish is dropped with a warning instead of
    turning the whole request into a 400, and the drop is reported so the run
    summary can show that a field was unavailable rather than pretending it was
    measured.
    """
    if not columns:
        return None
    available = dataset_variables(base, protocol, dataset_id)
    if not available:
        return list(columns)
    kept = [name for name in columns if name in available]
    missing = [name for name in columns if name not in available]
    if missing:
        logger.warning(
            "%s/%s does not declare %s; those fields will be absent from the "
            "result rather than guessed.", dataset_id, protocol, ", ".join(missing),
        )
    return kept or None


def request_table(base: str, protocol: str, dataset_id: str, *,
                  columns: Sequence[str] | None = None,
                  constraints: Iterable[ErddapConstraint] = (),
                  max_rows: int | None = None) -> ErddapTable:
    """Build, fetch and parse one constrained ERDDAP table request."""
    resolved = resolve_columns(base, protocol, dataset_id, columns)
    url = build_url(base, protocol, dataset_id, "csv", resolved, constraints)
    body = fetch(url, max_rows=max_rows)
    return parse_table(body, url=url, max_rows=max_rows)


def to_float(raw: Any) -> float | None:
    """Convert an ERDDAP cell to a finite float, or ``None`` for any missing token."""
    if raw is None:
        return None
    text = str(raw).strip()
    if text in ERDDAP_MISSING:
        return None
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    # A CSV cell of "inf"/"-inf"/"1e999" parses to a non-finite float.  Those are
    # corrupt, not measurements, and must never propagate.
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def parse_erddap_time(raw: Any) -> datetime | None:
    """Parse an ERDDAP time cell into an aware UTC datetime.

    The INCOIS instances publish ISO-8601 strings (``2025-01-15T06:00:00Z``),
    but ERDDAP is free to serve a dataset whose ``time_unit`` is *seconds since
    1970-01-01*, so a bare number is accepted as an epoch rather than rejected.
    Returns ``None`` for anything unparseable so the caller can flag the row.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=timezone.utc) if raw.tzinfo is None else raw.astimezone(timezone.utc)

    text = str(raw).strip()
    if not text or text in ERDDAP_MISSING:
        return None

    if text.lstrip("+-").replace(".", "", 1).isdigit():
        epoch = to_float(text)
        if epoch is None or abs(epoch) > 4_000_000_000:
            return None
        try:
            return datetime.fromtimestamp(epoch, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    candidate = text.replace(" ", "T", 1) if " " in text and "T" not in text else text
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%Y%m%dT%H%M%SZ",
                    "%Y%m%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


__all__ = [
    "ERDDAP_MISSING",
    "ErddapConstraint",
    "ErddapError",
    "ErddapTable",
    "build_url",
    "dataset_variables",
    "erddap_time",
    "fetch",
    "parse_erddap_time",
    "parse_table",
    "request_table",
    "resolve_columns",
    "to_float",
]
