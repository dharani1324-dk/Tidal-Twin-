"""Automatic Scientific Report Generator.

Composes a complete event/region investigation report including:
  - Event summary & fingerprint (DNA)
  - Timeline
  - Causal analysis
  - Historical comparisons
  - Data quality & confidence
  - Uncertainty
  - Future scenarios
  - Observation priorities

Formats: JSON, CSV, PDF (via reportlab if installed).
"""

import csv
import io
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.modules.ai.forensics.forensics import investigate, autopsy
from app.modules.ai.forensics.intelligence import (
    health_score, threat_chain, region_coverage,
    causal_chain, uncertainty_map, priority_map,
)
from app.modules.ai.forensics.fingerprint import similar_events
from app.modules.ai.validation.engine import future_windows, scenario_projection_multi


def _compose(db: Session, loc_id: int) -> dict:
    loc = db.query(OceanLocation).filter(OceanLocation.id == loc_id).first()
    inv = investigate(db, loc_id)
    aut = autopsy(db, loc_id)
    hc = health_score(db, loc_id)
    tc = threat_chain(db)
    tc_region = next((t for t in tc if t["location_id"] == loc_id), None)
    cov = next((c for c in region_coverage(db) if c["location_id"] == loc_id), None)
    unc = next((r for r in uncertainty_map(db).get("regions", []) if r["location_id"] == loc_id), None)
    pri = next((z for z in priority_map(db).get("zones", []) if z["location_id"] == loc_id), None)
    cc = causal_chain(db, loc_id)
    fw = future_windows(db, loc_id)
    sim = similar_events(db, aut.get("fingerprint", {}), limit=3) if aut.get("fingerprint") else []

    report = {
        "title": f"OceanVerse Scientific Report — {loc.name}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "location": loc.name,
        "location_id": loc_id,
        "report_version": "1.0",
        "sections": {
            "event_summary": {
                "change": inv.get("change"),
                "started_at": inv.get("started_at"),
                "variables_affected": inv.get("variables_affected"),
                "confidence": inv.get("confidence"),
            },
            "ocean_fingerprint": aut.get("fingerprint", {}),
            "investigation": {
                "depth_range": inv.get("depth_range"),
                "contributing_factors": inv.get("contributing_factors"),
                "evidence": inv.get("evidence"),
            },
            "causal_analysis": {
                "chain": cc.get("chain", []),
                "narrative": cc.get("narrative"),
                "ecosystem_risk": cc.get("ecosystem_risk"),
            },
            "similar_historical_events": sim,
            "data_quality": {
                "coverage": cov,
                "uncertainty": unc,
                "priority": pri,
                "health_score": hc[0] if hc else None,
            },
            "threat_awareness": tc_region,
            "uncertainty_analysis": aut.get("uncertainty"),
            "future_scenarios": fw.get("windows", []),
            "observation_priorities": aut.get("observation_priorities", []),
        },
    }
    return report


def report_json(db: Session, loc_id: int) -> dict:
    return _compose(db, loc_id)


def report_csv(db: Session, loc_id: int) -> str:
    data = _compose(db, loc_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Section", "Key", "Value"])
    writer.writerow(["Location", "Name", data["location"]])
    writer.writerow(["Generated", "Time", data["generated_at"]])

    inv = data["sections"]["investigation"]
    writer.writerow(["Investigation", "Confidence", data["sections"]["event_summary"]["confidence"]])
    for f in inv.get("contributing_factors", []):
        writer.writerow(["Factor", f["factor"], f["description"]])
    for e in inv.get("evidence", []):
        writer.writerow(["Evidence", e["label"], e["value"]])

    fp = data["sections"]["ocean_fingerprint"]
    for k, v in fp.items():
        if k != "tags":
            writer.writerow(["Fingerprint", k, v])

    for sim in data["sections"]["similar_historical_events"]:
        writer.writerow(["Similar Event", sim["label"], f"similarity {sim['similarity']}%"])

    for w in data["sections"]["future_scenarios"]:
        writer.writerow([f"Future {w['horizon_days']}d", "SST", w["projected_sst"]])
        writer.writerow([f"Future {w['horizon_days']}d", "Wave", w["projected_wave"]])
        writer.writerow([f"Future {w['horizon_days']}d", "Confidence", w["confidence"]])

    for p in data["sections"]["observation_priorities"]:
        writer.writerow(["Observation Priority", "—", p])

    return buf.getvalue()


def report_pdf(db: Session, loc_id: int) -> bytes | None:
    """Generate a PDF report via reportlab (returns bytes or None if not installed)."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                         TableStyle, HRFlowable)
    except ImportError:
        return None

    data = _compose(db, loc_id)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=20 * mm, bottomMargin=18 * mm)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Section", parent=styles["Heading2"],
                              fontSize=13, spaceAfter=6,
                              textColor=colors.HexColor("#0369a1")))
    styles.add(ParagraphStyle("Sub", parent=styles["Heading3"],
                              fontSize=10, spaceAfter=4, textColor=colors.HexColor("#0e7490")))
    styles.add(ParagraphStyle("BodySmall", parent=styles["BodyText"],
                              fontSize=9, leading=13))
    story = []

    story.append(Paragraph(data["title"], styles["Title"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"Generated: {data['generated_at']}", styles["BodySmall"]))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1")))

    story.append(Paragraph("1. Event Summary", styles["Section"]))
    es = data["sections"]["event_summary"]
    story.append(Paragraph(f"Confidence: <b>{es.get('confidence')}%</b>  |  "
                           f"Started: {es.get('started_at') or 'N/A'}", styles["BodySmall"]))
    story.append(Paragraph(f"Variables affected: {', '.join(es.get('variables_affected', [])) or '—'}",
                           styles["BodySmall"]))

    story.append(Paragraph("2. Ocean Fingerprint", styles["Section"]))
    fp = data["sections"]["ocean_fingerprint"]
    fp_rows = [[k, str(v)] for k, v in fp.items() if k != "tags"]
    if fp_rows:
        story.append(Table(fp_rows, colWidths=[120, 300],
                           style=TableStyle([
                               ("FONTSIZE", (0, 0), (-1, -1), 8),
                               ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
                               ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bae6fd")),
                           ])))
    story.append(Spacer(1, 8))

    story.append(Paragraph("3. Contributing Factors", styles["Section"]))
    for f in data["sections"]["investigation"].get("contributing_factors", []):
        story.append(Paragraph(
            f"<b>{f['factor']}</b> (weight {f.get('weight', 0):.2f}): {f['description']}",
            styles["BodySmall"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("4. Evidence", styles["Section"]))
    for e in data["sections"]["investigation"].get("evidence", []):
        story.append(Paragraph(f"<b>{e['label']}</b>: {e['value']} ({e.get('source', '')})",
                               styles["BodySmall"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("5. Causal Chain", styles["Section"]))
    narrative = data["sections"]["causal_analysis"].get("narrative", "")
    story.append(Paragraph(narrative, styles["BodySmall"]))
    story.append(Spacer(1, 6))
    chain = data["sections"]["causal_analysis"].get("chain", [])
    if chain:
        chain_rows = [[c["node"], f"{c['value']:.3f}", c["level"], c["description"]] for c in chain]
        story.append(Table(chain_rows, colWidths=[100, 55, 55, 210],
                           style=TableStyle([
                               ("FONTSIZE", (0, 0), (-1, -1), 8),
                               ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0fdf4")),
                               ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbf7d0")),
                           ])))
    story.append(Spacer(1, 8))

    story.append(Paragraph("6. Similar Historical Events", styles["Section"]))
    for s in data["sections"]["similar_historical_events"][:3]:
        story.append(Paragraph(
            f"<b>{s['label']}</b> — similarity {s['similarity']}%", styles["BodySmall"]))
    story.append(Spacer(1, 8))

    dq = data["sections"]["data_quality"]
    story.append(Paragraph("7. Data Quality & Uncertainty", styles["Section"]))
    if dq.get("coverage"):
        story.append(Paragraph(
            f"Coverage: {dq['coverage'].get('coverage_pct', 0)}%  |  "
            f"Confidence: {dq['coverage'].get('confidence', 0)}%", styles["BodySmall"]))
    if dq.get("uncertainty"):
        story.append(Paragraph(f"Uncertainty: {dq['uncertainty'].get('uncertainty', 0)}%", styles["BodySmall"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("8. Future Scenarios", styles["Section"]))
    for w in data["sections"]["future_scenarios"]:
        story.append(Paragraph(
            f"<b>{w['horizon_days']}d</b> — SST {w['projected_sst']}°C, "
            f"wave {w['projected_wave']}m, confidence {w['confidence']}%",
            styles["BodySmall"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("9. Observation Priorities", styles["Section"]))
    for p in data["sections"]["observation_priorities"]:
        story.append(Paragraph(f"• {p}", styles["BodySmall"]))

    doc.build(story)
    return buf.getvalue()
