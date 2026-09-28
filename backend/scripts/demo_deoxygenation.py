#!/usr/bin/env python3
"""
TidalTwin - Deoxygenation Intelligence Module Demo Script
==========================================================

This script demonstrates the complete end-to-end flow:
1. Ingest real Argo BGC float dissolved oxygen data
2. Ingest NOAA Hypoxia Watch reference data
3. Map samples to 8 coastal regions with confidence scores
4. Detect and rank hypoxic hotspots
5. Generate plain-language recommendations
6. Raise alerts in the platform's decision intelligence engine
7. Project hypoxic zone expansion trends

Run this after starting the backend server:
    python -m scripts.demo_deoxygenation
"""

import asyncio
import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.modules.ai.deoxygenation import engine
from app.models.dissolved_oxygen import DissolvedOxygenSample
from app.models.location import OceanLocation


async def demo_step(title: str, description: str):
    """Print a demo step with formatting."""
    print(f"\n{'='*70}")
    print(f"🔬 STEP: {title}")
    print(f"{'='*70}")
    print(f"📋 {description}")
    print("-" * 70)


async def demo_ingest():
    """Step 1: Ingest oxygen data from open sources."""
    await demo_step(
        "INGEST: Pull Real Open-Source Oxygen Data",
        "Fetch Argo BGC float DOXY measurements, NOAA Hypoxia Watch surveys, "
        "and peer-reviewed literature references for Indian Ocean OMZ/hypoxia."
    )
    
    db = SessionLocal()
    try:
        result = engine.ingest(db, limit=5)  # Small limit for demo
        print(f"✅ Ingestion Status: {result['status']}")
        print(f"📊 Connectors Used: {len(result['connectors'])}")
        for c in result['connectors']:
            print(f"   - {c['source']}: {'✅ Found' if c['found'] else '❌ Unavailable'} ({c.get('record_count', 0)} records)")
        print(f"📝 Records Accepted: {result['normalisation']['records_accepted']}")
        print(f"🗺️  Region Mapping: {result['region_mapping']}")
        print(f"💾 Persisted: {result['persistence']['inserted']} inserted, {result['persistence']['updated']} updated")
        return result
    finally:
        db.close()


async def demo_map_regions():
    """Step 2: Map unassigned samples to coastal regions."""
    await demo_step(
        "MAP: Assign Samples to 8 Coastal Regions",
        "Assign each oxygen measurement to its nearest monitored coastal region "
        "within 500km, computing confidence scores based on distance, data density, "
        "recency, and source reliability."
    )
    
    db = SessionLocal()
    try:
        result = engine.map_to_regions(db)
        print(f"✅ Assigned: {result['assigned']} samples to regions")
        print(f"⏭️  Skipped (out of radius): {result['skipped']} samples")
        print("📊 Samples per Region:")
        for region, count in result['region_counts'].items():
            if region != 'unassigned' and count > 0:
                print(f"   - {region}: {count} samples")
        return result
    finally:
        db.close()


async def demo_hotspots():
    """Step 3: Detect and rank hypoxic hotspots."""
    await demo_step(
        "DETECT: Identify & Rank Hypoxic Hotspots",
        "Cluster hypoxic samples by region/depth layer, compute statistics, "
        "and rank by priority (severity + persistence + spatial extent + trend + confidence). "
        "Generate plain-language recommendations for each hotspot."
    )
    
    db = SessionLocal()
    try:
        overview = engine.cached_overview(db)
        hotspots = overview['hotspots']['hotspots']
        
        print(f"🎯 Hotspot Category: {overview['hotspots']['anomaly_category']}")
        print(f"📈 Total Hotspots: {overview['hotspots']['hotspot_count']}")
        print(f"📋 Summary: {overview['hotspots']['recommendations']['summary']}")
        
        if hotspots:
            print("\n🔥 TOP HYPoxic HOTSPOTS:")
            for i, h in enumerate(hotspots[:5], 1):
                print(f"\n   {i}. {h['region']} ({h['depth_layer']})")
                print(f"      Severity: {h['severity']} | Priority: {h['priority']:.0f}/100")
                print(f"      Min O₂: {h['statistics']['min_do_mg_l']:.1f} mg/L")
                print(f"      Hypoxic Samples: {h['statistics']['n_hypoxic']}/{h['statistics']['n_samples']}")
                print(f"      Trend: {h['trend'].upper()}")
                print(f"      Confidence: {h['confidence']}%")
                print(f"      Action: {h['action'].replace('_', ' ').title()}")
                for rec in h['recommendations'][:2]:
                    print(f"      💡 {rec['text'][:80]}...")
        else:
            print("   No hypoxic hotspots detected above threshold.")
        
        return hotspots
    finally:
        db.close()


async def demo_trends():
    """Step 4: Analyze historical trends."""
    await demo_step(
        "TREND: Historical Oxygen Trend Analysis",
        "Analyze time series per region to detect if hypoxic zones are expanding, "
        "shrinking, or stable. Uses linear regression on oxygen values and hypoxic fraction."
    )
    
    db = SessionLocal()
    try:
        overview = engine.cached_overview(db)
        trends = overview['trends']['regions']
        
        print(f"📊 Regions Analyzed: {len(trends)}")
        for region_id, trend_data in trends.items():
            oxygen_trend = trend_data['oxygen_trend']
            hypoxic_trend = trend_data['hypoxic_trend']
            
            print(f"\n   {trend_data['region_name']} (ID: {region_id})")
            print(f"      Samples: {trend_data['n_samples']}")
            print(f"      O₂ Trend: {oxygen_trend['direction']} ({oxygen_trend['slope_mg_l_per_year']:+.3f} mg/L/yr, R²={oxygen_trend['r_squared']:.2f})")
            print(f"      Hypoxic Fraction Trend: {hypoxic_trend['direction']} ({hypoxic_trend.get('slope_per_year', 0):+.3f}/yr)")
            if hypoxic_trend.get('hypoxic_fractions'):
                print(f"      Yearly Hypoxic %: {hypoxic_trend['hypoxic_fractions']}")
        
        return trends
    finally:
        db.close()


async def demo_forecast():
    """Step 5: Project hypoxic zone expansion (stretch goal)."""
    await demo_step(
        "PROJECT: Hypoxic Zone Expansion Forecast",
        "Project future hypoxic zone extent based on historical trend. "
        "Returns PROJECTION (not forecast) with explicit uncertainty bands. "
        "This is a statistical projection assuming recent trends continue."
    )
    
    db = SessionLocal()
    try:
        overview = engine.cached_overview(db)
        regions = overview.get('coverage', {}).get('regions_without_data', [])
        
        # Get a region with data
        regions_with_data = overview.get('coverage', {}).get('regions_with_data', 0)
        if regions_with_data == 0:
            print("⚠️  No regions with data for projection")
            return
        
        # Use the first region with hotspots for demo
        hotspots = overview['hotspots']['hotspots']
        if not hotspots:
            print("⚠️  No hotspots for projection demo")
            return
        
        # Use the first hotspot's region
        region_id = hotspots[0]['region_id']
        regions_list = engine.resolve_monitored_regions(db)
        region = next((r for r in regions_list if r['region_id'] == region_id), None)
        
        if not region:
            print("⚠️  Region not found")
            return
        
        records = [engine._stored_to_normalized(row) for row in engine.load_records(db)]
        projection = engine.project_hypoxic_expansion(records, region, horizon_days=30)
        
        print(f"🔮 Projection for: {region['name']} (30-day horizon)")
        print(f"   Current Hypoxic Fraction: {projection['current']['hypoxic_fraction']:.1%}")
        print(f"   Current Est. Area: {projection['current']['estimated_area_km2']:.0f} km²")
        print(f"   Projected Hypoxic Fraction: {projection['projected']['hypoxic_fraction']:.1%}")
        print(f"   Projected Est. Area: {projection['projected']['estimated_area_km2']:.0f} km²")
        print(f"   Change: {projection['projected']['change']} ({projection['projected']['change_magnitude']:.1%})")
        print(f"   Uncertainty: {projection['uncertainty']['level']}")
        print(f"   Confidence: {projection['confidence']:.0f}%")
        print(f"   95% CI: [{projection['uncertainty']['lower_bound_fraction']:.1%}, {projection['uncertainty']['upper_bound_fraction']:.1%}]")
        print(f"\n   ⚠️  DISCLAIMER: {projection['disclaimer']}")
        
        return projection
    finally:
        db.close()


async def demo_alerts():
    """Step 6: Raise alerts in decision intelligence engine."""
    await demo_step(
        "ALERT: Raise Hypoxic Hotspots to Platform Alert Store",
        "Idempotently raise eligible hotspots (priority ≥ 60) as OceanAlert rows "
        "with source='deoxygenation'. Alerts carry plain-language descriptions "
        "and confidence scores for the decision intelligence dashboard."
    )
    
    db = SessionLocal()
    try:
        result = engine.emit_alerts(db, min_priority=60.0)
        print(f"📊 Evaluated: {result['evaluated']} hotspots")
        print(f"✅ Eligible (priority ≥ 60): {result['eligible']}")
        print(f"🆕 Created: {result['created']} new alerts")
        print(f"🔄 Refreshed: {result['refreshed']} existing alerts")
        print(f"📝 Note: {result['note']}")
        return result
    finally:
        db.close()


async def demo_visualization():
    """Step 7: 3D Visualization Preview."""
    await demo_step(
        "VISUALIZE: 3D Globe Oxygen Layer",
        "The Digital Twin globe now includes two oxygen layers:\n"
        "  1. 'Dissolved Oxygen' - Real GliderDAC BGC point samples\n"
        "  2. 'Hypoxic Zones' - Ranked hotspot beacons colored by severity\n"
        "     (Teal=Healthy, Amber=Low, Orange=Hypoxic, Red=Dead Zone)\n"
        "Both layers are toggleable, depth-sliceable, and time-scrubbable."
    )
    
    print("🎮 FRONTEND INTEGRATION:")
    print("   - Open http://localhost:5173/digital-twin")
    print("   - Toggle 'Hypoxic Zones' in Data Layers panel")
    print("   - Adjust opacity in Visual Style > Layer Opacity")
    print("   - Click hotspot beacons for details & recommendations")
    print("   - Use Event Replay scrubber for temporal trends")
    print("   - Color scale matches anomaly severity conventions")


async def demo_api_endpoints():
    """Step 8: API Endpoints Summary."""
    await demo_step(
        "API: Deoxygenation Intelligence Endpoints",
        "All endpoints follow the honesty contract: empty results carry reasons, "
        "no fabricated data, provenance on every response."
    )
    
    endpoints = [
        ("GET /api/v1/deoxygenation/overview", "Complete payload: hotspots + trends + coverage + sources"),
        ("GET /api/v1/deoxygenation/hotspots", "Ranked hypoxic zones with recommendations"),
        ("GET /api/v1/deoxygenation/trends", "Historical trend analysis per region"),
        ("GET /api/v1/deoxygenation/forecast?region_id=1&horizon_days=30", "Projected zone expansion with uncertainty"),
        ("GET /api/v1/deoxygenation/coverage", "Honest evidence report per region"),
        ("GET /api/v1/deoxygenation/sources", "Provenance, licenses, endpoints"),
        ("POST /api/v1/deoxygenation/ingest", "Pull Argo BGC + NOAA data now"),
        ("POST /api/v1/deoxygenation/map-regions", "Assign samples to 8 coastal regions"),
        ("POST /api/v1/deoxygenation/alerts/refresh", "Raise hotspots to alert store"),
    ]
    
    for endpoint, desc in endpoints:
        print(f"   {endpoint}")
        print(f"      → {desc}")


async def main():
    print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║          TIDALTWIN - DEOXYGENATION INTELLIGENCE MODULE DEMO               ║
║                                                                           ║
║  Open-source dissolved oxygen monitoring, hypoxia detection,             ║
║  and forecasting for 8 Indian Ocean coastal regions                       ║
╚═══════════════════════════════════════════════════════════════════════════╝
""")
    
    print("🌊 This demo runs against the live database.")
    print("   Ensure backend is running: cd backend && python -m uvicorn app.main:app --reload")
    print("   Ensure frontend is running: cd frontend && npm run dev")
    
    try:
        await demo_ingest()
        await demo_map_regions()
        await demo_hotspots()
        await demo_trends()
        await demo_forecast()
        await demo_alerts()
        await demo_visualization()
        await demo_api_endpoints()
        
        print(f"\n{'='*70}")
        print("✅ DEMO COMPLETE - Deoxygenation Module Fully Operational!")
        print(f"{'='*70}")
        print("""
📋 SUMMARY OF DELIVERABLES:
   1. ✅ Working ingestion pipeline (Argo BGC DOXY + NOAA Hypoxia + Literature)
   2. ✅ Normalized geospatial dataset joined to 8 coastal regions with confidence
   3. ✅ 3D color-graded oxygen layer (toggleable, depth-sliced, time-scrubbable)
   4. ✅ Decision intelligence integration: alerts + plain-language recommendations
   5. ✅ Predictive trend module: projections with uncertainty bands

🔬 DATA SOURCES (ALL OPEN, NO HARDWARE):
   - Argo BGC floats (DOXY variable) via GDAC API
   - NOAA Hypoxia Watch / Dead Zone surveys
   - World Ocean Database (WOD) historical profiles
   - Peer-reviewed literature (Arabian Sea OMZ, BoB OMZ, coastal hypoxia)

🎨 VISUALIZATION:
   - CesiumJS 3D globe with severity-colored hotspot beacons
   - Color ramp: Teal (>6 mg/L) → Amber (2-6) → Orange (0.5-2) → Red (<0.5)
   - Consistent with existing anomaly severity conventions
   - Depth slider & timeline scrubber integrated

⚡ HACKATHON DEMO FLOW:
   1. Click 'Ingest' button → real data pulls in
   2. Hypoxic Zones layer appears on globe
   3. Click hotspot → see severity, trend, recommendations
   4. Alert raised → appears in Monitoring/Intelligence panels
   5. Forecast tab → shows 30-day projection with uncertainty
""")
        
    except Exception as e:
        print(f"\n❌ Demo error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))