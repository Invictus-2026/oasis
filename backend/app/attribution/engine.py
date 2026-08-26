import math
import random
from datetime import timedelta
from app.core import config
from app.core.schemas import (
    VesselCandidate,
    ScoreBreakdown,
    ScoreWeights,
    AttributeResponse,
)

# Mocked vessel database for AIS Reconstruction
MOCK_VESSELS = [
    {"mmsi": "311000765", "name": "MV GULF SENTINEL", "type": "Crude Oil Tanker", "bearing": 128.0, "closest": 9.1, "has_gap": False, "gap_min": 0.0},
    {"mmsi": "366998210", "name": "SEACOR REVIVAL", "type": "Offshore Supply Vessel", "bearing": 205.0, "closest": 14.7, "has_gap": False, "gap_min": 0.0},
    {"mmsi": "356420119", "name": "MV ATLANTIC PIONEER", "type": "Container Ship", "bearing": 88.0, "closest": 21.3, "has_gap": False, "gap_min": 0.0},
    {"mmsi": "538007612", "name": "MV NORTHERN PETREL", "type": "Bulk Carrier", "bearing": 61.0, "closest": 6.4, "has_gap": True, "gap_min": 38.0},
    {"mmsi": "538008888", "name": "OCEAN ROVER", "type": "Fishing Vessel", "bearing": 15.0, "closest": 1.2, "has_gap": True, "gap_min": 120.0},
    {"mmsi": "311000999", "name": "GLOBAL PRIDE", "type": "Chemical/Oil Products Tanker", "bearing": 52.0, "closest": 1.8, "has_gap": True, "gap_min": 94.0},
    {"mmsi": "111000222", "name": "SEAWARD EXPLORER", "type": "Research Vessel", "bearing": 330.0, "closest": 19.5, "has_gap": False, "gap_min": 0.0},
    {"mmsi": "222000333", "name": "GULF BARGE 1", "type": "Tug/Barge", "bearing": 270.0, "closest": 4.5, "has_gap": False, "gap_min": 0.0},
]

def reconstruct_and_score(weights: ScoreWeights | None = None) -> AttributeResponse:
    """
    AIS Reconstruction & Scoring Engine.
    Implements a transparent weighted scoring engine for vessel attribution.
    """
    w = weights or ScoreWeights()
    rng = random.Random(42)  # Deterministic for consistency in UI
    
    candidates = []
    
    # 1. AIS RECONSTRUCTION (Filtering Pipeline)
    # Simulate finding 2,341 raw records, spatial filtering down to 45, temporal down to len(MOCK_VESSELS).
    total_in_region = 45
    
    # 2. SCORING ENGINE
    for v in MOCK_VESSELS:
        # A. Proximity (closer is more suspicious)
        # Max score at 0km, decays to 0 at 25km.
        proximity_score = max(0.0, 1.0 - (v["closest"] / config.ATTRIBUTION_RADIUS_KM))
        
        # B. Temporal Match (simulated based on closest approach)
        temporal_score = max(0.0, 1.0 - (v["closest"] / 40.0))
        
        # C. Trajectory & Heading
        # Assume drift heading was 48 degrees
        drift_heading = 48.0
        heading_diff = abs(v["bearing"] - drift_heading)
        if heading_diff > 180:
            heading_diff = 360 - heading_diff
        heading_score = max(0.0, 1.0 - (heading_diff / 180.0))
        trajectory_score = max(0.0, heading_score - 0.1) # Correlated
        
        # D. AIS Gap & Behaviour
        gap_score = min(1.0, v["gap_min"] / 90.0) if v["has_gap"] else 0.0
        
        # Context (Oil tankers and fishing vessels might be higher risk in this region)
        context_score = 0.5
        if "Oil" in v["type"]:
            context_score = 1.0
        elif "Fishing" in v["type"]:
            context_score = 0.8
            
        behaviour_score = 0.9 if v["has_gap"] and gap_score > 0.5 else 0.2
        
        # Compile Breakdown
        breakdown = ScoreBreakdown(
            proximity=round(proximity_score, 3),
            temporal_overlap=round(temporal_score, 3),
            heading_consistency=round(heading_score, 3),
            trajectory_alignment=round(trajectory_score, 3),
            behavioural_anomaly=round(behaviour_score, 3),
            ais_gap_penalty=round(gap_score, 3),
            context_suspicion=round(context_score, 3),
        )
        
        # Calculate Final Weighted Score
        final_score = (
            (breakdown.proximity * w.proximity) +
            (breakdown.temporal_overlap * w.temporal_overlap) +
            (breakdown.trajectory_alignment * w.trajectory_alignment) +
            (breakdown.heading_consistency * w.heading_consistency) +
            (breakdown.behavioural_anomaly * w.behavioural_anomaly) +
            (breakdown.ais_gap_penalty * w.ais_gap_penalty) +
            (breakdown.context_suspicion * w.context_suspicion)
        )
        
        flags = []
        if gap_score > 0.5:
            flags.append("DARK_VESSEL")
        if behaviour_score > 0.8:
            flags.append("ROUTE_DEVIATION")
        if v["closest"] < 2.0:
            flags.append("DANGER_CLOSE")
            
        # Explanations for transparency (no unexplained AI!)
        narrative = f"Vessel passed within {v['closest']}km of the estimated origin."
        if gap_score > 0:
            narrative += f" A {int(v['gap_min'])} minute AIS transmission gap was detected near the spill origin."
        if "Oil" in v["type"]:
            narrative += " Vessel type is high-risk for mineral oil spills."
            
        candidates.append(
            VesselCandidate(
                mmsi=v["mmsi"],
                name=v["name"],
                vessel_type=v["type"],
                closest_approach_km=v["closest"],
                score=round(final_score, 3),
                breakdown=breakdown,
                flags=flags,
                narrative=narrative,
            )
        )
        
    # Sort candidates by score descending
    candidates.sort(key=lambda c: c.score, reverse=True)
    
    # Rerank to assign 1, 2, 3...
    for i, c in enumerate(candidates):
        c.rank = i + 1

    return AttributeResponse(
        total_vessels_in_region=total_in_region,
        after_filter=len(candidates),
        candidates=candidates,
    )
