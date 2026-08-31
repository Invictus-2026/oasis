"""
Phase 5 — origin-time-and-location search.

Given an observed slick, search candidate (release location, release time)
pairs over the previous `max_age_hours` and rank them by how well each
candidate's own forward simulation reproduces the observed slick.

Method, per candidate release time t (hourly by default, previous 24 h):

  1. PROPOSE. Run a real backward Lagrangian simulation (drift/simulate.py,
     itself Phase 4's engine) from the observed slick to age t. Its centroid
     is the candidate release location. This is a real simulation, not a
     lookup — the same equations drift/lagrangian.py uses for the existing
     /api/drift/hindcast path.
  2. VERIFY. Run a real FORWARD simulation from that candidate location at
     that candidate time, forward to the detection time. This produces an
     independent particle cloud that the candidate PREDICTS the slick should
     look like.
  3. SCORE. Compare the predicted cloud to the OBSERVED slick polygon on five
     documented metrics (spatial overlap, centroid distance, shape
     similarity, orientation similarity, particle-density similarity),
     combined into one weighted composite score (SCORE_WEIGHTS below).
  4. RANK. Sort candidates by composite score, descending.

The best candidate's release time is the estimated release time; age is
detection_time - release_time, always returned with an explicit
[min, max] uncertainty window from the candidates that scored close to the
best — never a bare point estimate. Okubo-derived width-inversion age
(detection/age.py) is folded in as ONE input to the composite (see
`_age_plausibility` and `SCORE_WEIGHTS`), never the sole determinant: the
ranking is driven primarily by whether a candidate's own simulated cloud
actually reproduces the observed geometry, which is the only way to make use
of the "compare simulated particles with observed slick" requirement rather
than trusting a closed-form age formula on its own.

KNOWN LIMITATION, stated rather than tuned away: spatial_overlap and
density_similarity are mechanically biased toward SHORTER candidate ages.
Less elapsed time means less diffusion spread, which produces a tighter
predicted cloud and, all else equal, a higher overlap/density score
regardless of whether the release location is actually correct — diffusion
spreads a cloud out, and a more spread-out cloud is intrinsically harder to
land precisely on top of a small observed polygon. Measured against the
frozen case study (true age 8.0 h), the search currently favours ages
1-2 h shorter than truth for exactly this reason; centroid_distance_km stays
roughly flat across candidate ages, confirming the bias sits specifically in
the spread-sensitive terms, not in the location estimate itself. The
Okubo-derived age_plausibility term (with length_km correctly supplied,
see _age_plausibility) DOES weight toward the true age here, but is
deliberately capped at a 15% composite adjustment (SCORE_WEIGHTS is a
geometry-driven composite, not an age-formula-driven one — see this
module's own design rule above) so it cannot override a genuinely poor
geometry match, which means it also cannot always fully correct this bias.
This is disclosed rather than fixed by re-weighting toward one ground-truth
case, which would be the kind of curve-fitting "no hard-coded scientific
result" is meant to rule out. A structural fix (e.g. normalising
overlap/density by the candidate's own predicted spread) is a candidate for
future work, not a same-session tuning pass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
from pydantic import BaseModel, Field

from app.detection import age as age_mod
from app.drift import cone as cone_mod
from app.drift import simulate
from app.drift.lagrangian import _points_in_poly
from app.environment.base import EnvironmentalDataProvider

KM_PER_DEG_LAT = 110.574


def _km_per_deg_lon(lat: float) -> float:
    return 111.320 * math.cos(math.radians(lat))


def _line_source_ring(lon: float, lat: float, length_km: float, bearing_deg: float) -> list[list[float]]:
    """A thin rectangle centred on (lon, lat), oriented along bearing_deg,
    spanning length_km — the seed geometry for an underway-vessel discharge.

    A point release cannot reproduce an elongated trail no matter how correct
    the release time and location are: the trail's length reflects distance
    travelled while discharging, not spreading (see detection/age.py's own
    line-source assumption). Modelling the release the same way here is what
    lets shape_similarity and density_similarity be real discriminators
    instead of failing identically for every candidate.
    """
    half_len_km = max(length_km, 0.05) / 2.0
    half_width_km = 0.05  # a nominal narrow discharge track, not the observed width
    theta = math.radians(bearing_deg)
    dx_km, dy_km = math.sin(theta), math.cos(theta)  # unit vector along the bearing
    px_km, py_km = math.cos(theta), -math.sin(theta)  # perpendicular unit vector

    klon, klat = _km_per_deg_lon(lat), KM_PER_DEG_LAT
    corners_km = [
        (-half_len_km, -half_width_km), (half_len_km, -half_width_km),
        (half_len_km, half_width_km), (-half_len_km, half_width_km),
    ]
    ring = [
        [lon + (t * dx_km + w * px_km) / klon, lat + (t * dy_km + w * py_km) / klat]
        for t, w in corners_km
    ]
    ring.append(ring[0])
    return ring


# Composite score weights. Documented and summing to 1 so the score is
# auditable rather than a magic number — same house rule as classify() in
# detection/classical.py and the attribution ScoreWeights. No single term
# dominates (all < 0.6): a candidate cannot win on geometry match alone
# without also landing near the observed centroid, and cannot win on the
# Okubo-derived age plausibility alone without its own simulated cloud
# actually resembling the slick.
SCORE_WEIGHTS: dict[str, float] = {
    "spatial_overlap": 0.30,        # does the predicted cloud actually cover the observed slick?
    "centroid_distance": 0.20,      # how far off is the predicted center of mass?
    "shape_similarity": 0.20,       # compactness/elongation match
    "orientation_similarity": 0.15, # principal-axis bearing match
    "density_similarity": 0.15,     # does the predicted spread match the observed spread?
}

# Beyond this the centroid-distance term saturates at 0 — a candidate whose
# predicted cloud lands 50+ km from the observed slick is not a contender
# regardless of how well-shaped its cloud happens to be.
CENTROID_DISTANCE_SATURATION_KM = 50.0


class ObservedSlick(BaseModel):
    """The comparison target: what Stage 1 detected, reduced to the fields
    origin search needs. Deliberately not the full API `Slick` schema, so
    this module has no dependency on the detection API layer."""

    polygon: list[list[float]] = Field(description="closed [lon, lat] ring")
    detected_at: datetime
    area_km2: float
    orientation_deg: float
    elongation: float
    compactness: float
    length_km: float | None = Field(
        default=None,
        description="major-axis extent, if known; used to seed a line-source release for an "
                    "elongated (underway-discharge) slick instead of a point release",
    )

    @property
    def centroid(self) -> tuple[float, float]:
        pts = np.asarray(self.polygon)
        return float(pts[:, 0].mean()), float(pts[:, 1].mean())

    @property
    def is_elongated(self) -> bool:
        """Above this, a point release cannot physically reproduce the
        observed shape — this project's own age model already treats such a
        slick as a line source (detection/age.py), not a point release; the
        forward-verification seeding follows the same assumption."""
        return self.elongation > 3.0


class SearchConfig(BaseModel):
    max_age_hours: float = Field(default=24.0, gt=0.0, le=24 * 14)
    time_step_hours: float = Field(default=1.0, gt=0.0, le=24.0)
    particle_count: int = Field(default=150, gt=0, le=5000)
    timestep_minutes: float = Field(default=15.0, gt=0.0, le=1440.0)
    windage_coefficient: float = Field(default=0.03, ge=0.0, le=0.2)
    diffusion_coefficient_m2s: float | None = Field(default=None, ge=0.0)


@dataclass
class ComparisonMetrics:
    """The five required comparison metrics plus the documented composite."""

    spatial_overlap: float
    centroid_distance_km: float
    shape_similarity: float
    orientation_similarity: float
    density_similarity: float
    composite_score: float


@dataclass
class Candidate:
    release_time_utc: datetime
    age_hours: float
    origin_lon: float
    origin_lat: float
    simulated_positions: np.ndarray  # (n, 2) forward-predicted cloud at detection time
    metrics: ComparisonMetrics
    age_plausibility: float  # how well this candidate's age matches the Okubo bracket, 0-1


@dataclass
class SearchResult:
    observed: ObservedSlick
    candidates: list[Candidate]
    ranked: list[Candidate]
    config: SearchConfig
    provider_name: str

    @property
    def best(self) -> Candidate:
        return self.ranked[0]

    @property
    def region_50(self) -> dict | None:
        return self._region(0.50)

    @property
    def region_90(self) -> dict | None:
        return self._region(0.90)

    def _region(self, fraction: float) -> dict | None:
        """The 50%/90% region is built from the BEST candidate's own
        simulated cloud (its forward-predicted spread), not from scattering
        candidate release points — that spread is what a Lagrangian ensemble's
        containment region is supposed to represent (see cone.py), and reusing
        it here keeps this consistent with the existing hindcast's semantics.
        """
        ring = cone_mod.containment_polygon(self.best.simulated_positions, fraction)
        return {"type": "Polygon", "coordinates": [ring]} if ring else None

    @property
    def estimated_age_hours(self) -> float:
        return self.best.age_hours

    @property
    def age_uncertainty_hours(self) -> tuple[float, float]:
        """Not a formula-derived bracket alone: the window spans every
        candidate whose composite score comes within 15% of the best, which
        is what makes this an OPTIMIZATION result — candidates that fit the
        observed geometry nearly as well as the winner bound how sure we can
        be about exactly when release happened."""
        if len(self.ranked) == 1:
            a = self.ranked[0].age_hours
            return (max(0.0, a - self.config.time_step_hours), a + self.config.time_step_hours)

        best_score = self.ranked[0].metrics.composite_score
        threshold = best_score * 0.85
        close = [c for c in self.ranked if c.metrics.composite_score >= threshold] or [self.ranked[0]]
        ages = [c.age_hours for c in close]
        lo, hi = min(ages), max(ages)
        if hi - lo < self.config.time_step_hours:
            # Never collapse to a single instant: even a decisive winner still
            # carries at least one time-step's worth of honest uncertainty.
            hi = lo + self.config.time_step_hours
        return (round(max(0.0, lo), 2), round(hi, 2))

    @property
    def confidence(self) -> str:
        """Qualitative only, and deliberately hard to earn "high": both a
        decisive score margin over the runner-up AND a tight age window are
        required, so a single strong-looking number can't overstate certainty
        on its own."""
        if len(self.ranked) < 2:
            return "low"
        top, second = self.ranked[0].metrics.composite_score, self.ranked[1].metrics.composite_score
        margin = top - second
        lo, hi = self.age_uncertainty_hours
        window = hi - lo

        if top > 0.6 and margin > 0.08 and window <= 3 * self.config.time_step_hours:
            return "high"
        if top > 0.35 and margin > 0.03:
            return "medium"
        return "low"

    def to_geojson(self) -> dict:
        features = []
        if self.region_90:
            features.append({"type": "Feature", "geometry": self.region_90,
                              "properties": {"kind": "origin_90", "percentile": 90}})
        if self.region_50:
            features.append({"type": "Feature", "geometry": self.region_50,
                              "properties": {"kind": "origin_50", "percentile": 50}})
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(self.best.origin_lon, 6),
                                                             round(self.best.origin_lat, 6)]},
            "properties": {
                "kind": "best_origin",
                "release_time_utc": self.best.release_time_utc.isoformat(),
                "age_hours": round(self.best.age_hours, 2),
                "composite_score": round(self.best.metrics.composite_score, 4),
            },
        })

        lo, hi = self.age_uncertainty_hours
        return {
            "type": "FeatureCollection",
            "features": features,
            "properties": {
                "estimated_age_hours": round(self.estimated_age_hours, 2),
                "age_uncertainty_hours": [lo, hi],
                "confidence": self.confidence,
                "release_time_utc": self.best.release_time_utc.isoformat(),
                "detection_time_utc": self.observed.detected_at.isoformat(),
                "n_candidates": len(self.candidates),
                "provider": self.provider_name,
                "search_window_hours": self.config.max_age_hours,
            },
        }


# ---------------------------------------------------------------------------
# Comparison metrics
# ---------------------------------------------------------------------------


def _spatial_overlap(cloud: np.ndarray, observed: ObservedSlick) -> float:
    """Fraction of the simulated cloud that falls inside the observed
    polygon — a real (if crude) IoU-style proxy without needing to rasterise
    both shapes onto a shared grid."""
    poly = np.asarray(observed.polygon)
    inside = _points_in_poly(cloud, poly)
    return float(inside.mean())


def _centroid_distance_km(cloud: np.ndarray, observed: ObservedSlick) -> float:
    clon, clat = observed.centroid
    slon, slat = float(cloud[:, 0].mean()), float(cloud[:, 1].mean())
    dx = (slon - clon) * _km_per_deg_lon(clat)
    dy = (slat - clat) * KM_PER_DEG_LAT
    return math.hypot(dx, dy)


def _cloud_shape(cloud: np.ndarray) -> tuple[float, float, float]:
    """(elongation, orientation_deg, compactness-like spread ratio) of the
    simulated cloud, via the same second-moment construction
    detection/classical.py uses for the observed slick, so the two are
    comparable on equal footing."""
    lon, lat = cloud[:, 0], cloud[:, 1]
    lat0 = float(lat.mean())
    x = (lon - lon.mean()) * _km_per_deg_lon(lat0)
    y = (lat - lat.mean()) * KM_PER_DEG_LAT
    if len(x) < 3 or (np.std(x) + np.std(y)) < 1e-9:
        return 1.0, 0.0, 1.0

    c = np.cov(np.vstack([x, y]))
    evals, evecs = np.linalg.eigh(c)
    lo, hi = max(float(evals[0]), 1e-9), max(float(evals[1]), 1e-9)
    major = evecs[:, int(np.argmax(evals))]
    bearing = math.degrees(math.atan2(major[0], major[1])) % 180.0
    elongation = math.sqrt(hi / lo)
    return elongation, bearing, elongation


def _shape_similarity(cloud: np.ndarray, observed: ObservedSlick) -> float:
    elong, _, _ = _cloud_shape(cloud)
    # Ratio-based similarity: 1.0 for an exact match, decaying symmetrically
    # whichever direction the elongation differs.
    ratio = min(elong, observed.elongation) / max(elong, observed.elongation, 1e-6)
    return float(np.clip(ratio, 0.0, 1.0))


def _orientation_similarity(cloud: np.ndarray, observed: ObservedSlick) -> float:
    _, bearing, _ = _cloud_shape(cloud)
    diff = abs(bearing - observed.orientation_deg) % 180.0
    diff = min(diff, 180.0 - diff)  # a bearing and its 180-degree flip are the same axis
    return float(np.clip(1.0 - diff / 90.0, 0.0, 1.0))


def _density_similarity(cloud: np.ndarray, observed: ObservedSlick) -> float:
    """What fraction of the predicted PARTICLE MASS lands inside the observed
    footprint, weighted by how concentrated it is there.

    Distinct from spatial_overlap (which only asks whether particles are
    inside/outside the polygon): this rewards a candidate whose particles are
    actually DENSE over the observed slick, not merely present at its edge.
    A raw footprint-area comparison was tried first and rejected — an 8h
    diffusion run spreads particles far beyond the tight polygon a detector
    draws around the visible oil, so cloud footprint area and observed
    detected area are not comparable quantities; the fraction of particle
    mass concentrated over the observed footprint is.
    """
    poly = np.asarray(observed.polygon)
    inside = _points_in_poly(cloud, poly)
    frac_inside = float(inside.mean())
    if frac_inside == 0.0:
        return 0.0

    # Among the particles that DID land inside, how tightly are they packed
    # relative to the observed slick's own footprint? A candidate whose
    # in-polygon particles are bunched in one corner is a worse density match
    # than one whose in-polygon particles fill the polygon's extent.
    poly_diag_km = math.hypot(
        (poly[:, 0].max() - poly[:, 0].min()) * _km_per_deg_lon(float(poly[:, 1].mean())),
        (poly[:, 1].max() - poly[:, 1].min()) * KM_PER_DEG_LAT,
    )
    inside_pts = cloud[inside]
    if len(inside_pts) < 2 or poly_diag_km <= 0:
        coverage = 0.0
    else:
        spread_km = math.hypot(
            float(np.std(inside_pts[:, 0])) * _km_per_deg_lon(float(inside_pts[:, 1].mean())),
            float(np.std(inside_pts[:, 1])) * KM_PER_DEG_LAT,
        )
        coverage = float(np.clip(spread_km / (poly_diag_km / 4.0), 0.0, 1.0))

    return float(np.clip(0.7 * frac_inside + 0.3 * coverage, 0.0, 1.0))


def compare(cloud: np.ndarray, observed: ObservedSlick) -> ComparisonMetrics:
    """Stage 3 — score one candidate's predicted cloud against the observed
    slick on all five required metrics, combined into the documented
    composite (SCORE_WEIGHTS)."""
    overlap = _spatial_overlap(cloud, observed)
    dist_km = _centroid_distance_km(cloud, observed)
    shape = _shape_similarity(cloud, observed)
    orient = _orientation_similarity(cloud, observed)
    density = _density_similarity(cloud, observed)

    dist_score = float(np.clip(1.0 - dist_km / CENTROID_DISTANCE_SATURATION_KM, 0.0, 1.0))

    composite = (
        SCORE_WEIGHTS["spatial_overlap"] * overlap
        + SCORE_WEIGHTS["centroid_distance"] * dist_score
        + SCORE_WEIGHTS["shape_similarity"] * shape
        + SCORE_WEIGHTS["orientation_similarity"] * orient
        + SCORE_WEIGHTS["density_similarity"] * density
    )

    return ComparisonMetrics(
        spatial_overlap=round(overlap, 4),
        centroid_distance_km=round(dist_km, 3),
        shape_similarity=round(shape, 4),
        orientation_similarity=round(orient, 4),
        density_similarity=round(density, 4),
        composite_score=round(float(np.clip(composite, 0.0, 1.0)), 4),
    )


def _age_plausibility(age_hours: float, observed: ObservedSlick, contrast_db: float | None) -> float:
    """How well a candidate age matches the Okubo width-inversion bracket
    (detection/age.py) — an EMPIRICAL CONSTRAINT folded into ranking as one
    signal among five geometry-comparison metrics, never returned or used as
    the age estimate itself. A candidate outside the plausible bracket is not
    rejected outright, only nudged down, because the bracket carries its own
    factor-of-2 uncertainty and should not veto a candidate whose actual
    simulated cloud fits the observed slick well.
    """
    # Pass length_km when known: age.py's own docstring states that treating
    # an elongated trail as a point-source blob overestimates age by roughly
    # an order of magnitude (Fay spreading vs. the correct width-inversion
    # model) — using length_km=None here for an elongated slick would silently
    # reintroduce exactly the error that module exists to avoid.
    bracket = age_mod.estimate(observed.area_km2, contrast_db or 5.0, length_km=observed.length_km)
    if not bracket:
        return 0.5  # no signal either way
    lo, hi = bracket["min_hours"], bracket["max_hours"]
    if lo <= age_hours <= hi:
        return 1.0
    span = max(hi - lo, 1.0)
    dist = min(abs(age_hours - lo), abs(age_hours - hi))
    return float(np.clip(1.0 - dist / span, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def search(
    observed: ObservedSlick,
    *,
    provider: EnvironmentalDataProvider,
    config: SearchConfig | None = None,
    seed: int = 42,
) -> SearchResult:
    """Stages 1-5: generate candidates, run a real simulation per candidate,
    score against the observed slick, and rank."""
    cfg = config or SearchConfig()
    n_candidates = max(1, int(round(cfg.max_age_hours / cfg.time_step_hours)))

    candidates: list[Candidate] = []
    for i in range(1, n_candidates + 1):
        age_hours = i * cfg.time_step_hours
        release_time = observed.detected_at - timedelta(hours=age_hours)
        candidate_seed = seed + i

        # -- PROPOSE: real backward simulation from the observed slick ------
        back_cfg = simulate.SimulationConfig(
            particle_count=cfg.particle_count, timestep_minutes=cfg.timestep_minutes,
            duration_hours=age_hours, windage_coefficient=cfg.windage_coefficient,
            diffusion_coefficient_m2s=cfg.diffusion_coefficient_m2s,
        )
        back_result = simulate.run(
            observed.polygon, provider=provider, start_time=observed.detected_at,
            direction=-1, config=back_cfg, seed=candidate_seed,
        )
        origin_lon = float(back_result.final_positions()[:, 0].mean())
        origin_lat = float(back_result.final_positions()[:, 1].mean())

        # -- VERIFY: real forward simulation from the candidate release -----
        # An elongated observed slick is a line source (a vessel discharging
        # while underway), not a point release — see _line_source_ring and
        # detection/age.py's line-source assumption. Seeding a point release
        # for such a slick would make shape_similarity and density_similarity
        # fail identically for every candidate, regardless of how correct the
        # origin/time actually is.
        if observed.is_elongated and observed.length_km:
            seed_geometry = _line_source_ring(
                origin_lon, origin_lat, observed.length_km, observed.orientation_deg,
            )
            fwd_seed_mode = "polygon"
        else:
            seed_geometry = [[origin_lon, origin_lat]]
            fwd_seed_mode = "point"

        fwd_cfg = simulate.SimulationConfig(
            particle_count=cfg.particle_count, timestep_minutes=cfg.timestep_minutes,
            duration_hours=age_hours, windage_coefficient=cfg.windage_coefficient,
            diffusion_coefficient_m2s=cfg.diffusion_coefficient_m2s,
        )
        fwd_result = simulate.run(
            seed_geometry, provider=provider, start_time=release_time,
            direction=+1, config=fwd_cfg, seed=candidate_seed + 1_000_000, seed_mode=fwd_seed_mode,
        )
        predicted_cloud = fwd_result.final_positions()

        # -- SCORE -----------------------------------------------------------
        metrics = compare(predicted_cloud, observed)
        plausibility = _age_plausibility(age_hours, observed, contrast_db=None)
        # Fold the Okubo-derived plausibility in as a small nudge on top of
        # the geometry-driven composite — see module docstring: it is a
        # constraint, not the estimator. Capped contribution keeps it a minor
        # term even at full weight.
        adjusted = float(np.clip(metrics.composite_score * (0.85 + 0.15 * plausibility), 0.0, 1.0))
        metrics.composite_score = round(adjusted, 4)

        candidates.append(Candidate(
            release_time_utc=release_time,
            age_hours=age_hours,
            origin_lon=origin_lon,
            origin_lat=origin_lat,
            simulated_positions=predicted_cloud,
            metrics=metrics,
            age_plausibility=round(plausibility, 4),
        ))

    ranked = sorted(candidates, key=lambda c: c.metrics.composite_score, reverse=True)
    provider_name = getattr(provider, "name", provider.__class__.__name__)

    return SearchResult(
        observed=observed, candidates=candidates, ranked=ranked,
        config=cfg, provider_name=provider_name,
    )
