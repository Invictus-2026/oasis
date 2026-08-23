#!/usr/bin/env python3
"""
Build the frozen case-study bundle in data/case/.

The bundle is the single immutable input every downstream phase is developed
against. Re-running this script reproduces it byte-for-byte (all randomness is
seeded), which is what makes the pipeline's results auditable.

Design: each input has a REAL source and, where credentials or bandwidth make
the real source unavailable today, a physically-plausible SYNTHESISED stand-in.
Which one was used is recorded per-source in case.json and surfaced in the UI.
Nothing is silently faked.

    backend/.venv/bin/python scripts/build_case.py

Inputs it looks for in data/raw/ (all optional; it degrades honestly):
    masks/Mask_oil/00250.tif            official Zenodo oil mask  [REAL]
    masks/Mask_lookalike/*.tif          official Zenodo lookalike masks [REAL]
    AIS_2023_06_15.zip                  NOAA AccessAIS day file   [REAL]
    era5_wind.nc / cmems_currents.nc    forcing, if you have credentials
"""

from __future__ import annotations

import json
import math
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import config  # noqa: E402

RAW = ROOT / "data" / "raw"
CASE = ROOT / "data" / "case"

SEED = 20230615
MASK_ID = "00250"          # chosen in Phase 1: fully contained discharge trail
GRID = 1024                # working raster size, downsampled from the 2048 mask

# The mask is a shape, not a georeferenced extent, so we choose its real-world
# scale and position. 34 km is a realistic length for an underway discharge
# trail; stretching the mask across the whole bbox would have implied a
# 188 km2 slick, which is Deepwater-Horizon scale and not credible for one
# vessel. Position sits NE of centre so that backtracking SW against the drift
# keeps the origin comfortably inside the bbox and inside AIS coverage.
SLICK_LENGTH_KM = 34.0
SLICK_CENTER_FRAC = (0.62, 0.42)   # (x from west, y from north) in [0,1]

# Scenario timing
ACQUIRED = config.ACQUIRED_AT                      # 2023-06-15 12:00 UTC
DRIFT_HOURS = 8.0                                  # slick age at acquisition
ORIGIN_TIME = ACQUIRED - timedelta(hours=DRIFT_HOURS)

# Mean forcing for the scenario. Chosen so the slick drifts NE at a realistic
# ~0.15 m/s net, which is typical for the northern Gulf in June.
MEAN_CURRENT_MS = (0.11, 0.08)     # (u east, v north) m/s
MEAN_WIND_MS = (3.6, 2.4)          # 10 m wind, m/s — above the 3 m/s SAR floor
WIND_FACTOR = config.DRIFT_WIND_FACTOR

POLLUTER_MMSI = "367301820"
POLLUTER_NAME = "MV KESTREL TRADER"
POLLUTER_TYPE = "Chemical/Oil Products Tanker"
POLLUTER_GAP_MINUTES = 94.0

KM_PER_DEG_LAT = 110.574


def km_per_deg_lon(lat: float) -> float:
    return 111.320 * math.cos(math.radians(lat))


@dataclass
class Source:
    name: str
    kind: str
    real: bool
    source_url: str | None = None
    licence: str | None = None
    note: str | None = None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "source_url": self.source_url,
            "licence": self.licence,
            "is_synthetic": not self.real,
            "note": self.note,
        }


@dataclass
class Build:
    sources: list[Source] = field(default_factory=list)

    def add(self, s: Source) -> None:
        self.sources.append(s)
        tag = "REAL " if s.real else "SYNTH"
        print(f"  [{tag}] {s.name}")


# ---------------------------------------------------------------------------
# Geo helpers
# ---------------------------------------------------------------------------

def pixel_to_lonlat(col: np.ndarray, row: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Map raster pixel coords (origin top-left) onto the case bbox."""
    b = config.CASE_BBOX
    lon = b["west"] + (col / (GRID - 1)) * (b["east"] - b["west"])
    lat = b["north"] - (row / (GRID - 1)) * (b["north"] - b["south"])
    return lon, lat


def offset_km(lon: float, lat: float, dx: float, dy: float) -> tuple[float, float]:
    return (lon + dx / km_per_deg_lon(lat), lat + dy / KM_PER_DEG_LAT)


# ---------------------------------------------------------------------------
# 1. Oil mask — the real official ground truth
# ---------------------------------------------------------------------------

def place_mask(m: np.ndarray) -> np.ndarray:
    """Scale and position the mask shape onto the case raster.

    The Zenodo mask carries real slick MORPHOLOGY but no georeferencing, so its
    real-world size and location are ours to choose. We preserve its aspect
    ratio exactly and scale it so the trail spans SLICK_LENGTH_KM.
    """
    from PIL import Image

    ys, xs = np.nonzero(m)
    crop = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

    # Major-axis length of the shape, in source pixels.
    cy, cx = ys.mean() - ys.min(), xs.mean() - xs.min()
    c = np.cov(np.vstack([xs - xs.min(), ys - ys.min()]))
    evals, evecs = np.linalg.eigh(c)
    major = evecs[:, int(np.argmax(evals))]
    t = (xs - xs.min() - cx) * major[0] + (ys - ys.min() - cy) * major[1]
    axis_px = float(t.max() - t.min())

    # Target: axis_px source pixels must become SLICK_LENGTH_KM on the ground.
    b = config.CASE_BBOX
    w_km = (b["east"] - b["west"]) * km_per_deg_lon(config.CASE_CENTER[1])
    km_per_px = w_km / GRID
    scale = (SLICK_LENGTH_KM / km_per_px) / axis_px

    new_w = max(2, int(round(crop.shape[1] * scale)))
    new_h = max(2, int(round(crop.shape[0] * scale)))
    small = np.array(
        Image.fromarray(crop.astype(np.uint8) * 255).resize((new_w, new_h), Image.NEAREST)
    ) > 0

    canvas = np.zeros((GRID, GRID), dtype=bool)
    cx_t = int(SLICK_CENTER_FRAC[0] * GRID)
    cy_t = int(SLICK_CENTER_FRAC[1] * GRID)
    x0, y0 = cx_t - new_w // 2, cy_t - new_h // 2
    x0, y0 = max(0, min(GRID - new_w, x0)), max(0, min(GRID - new_h, y0))
    canvas[y0:y0 + new_h, x0:x0 + new_w] = small
    return canvas


def load_oil_mask(b: Build) -> np.ndarray:
    from PIL import Image

    p = RAW / "masks" / "Mask_oil" / f"{MASK_ID}.tif"
    if not p.exists():
        raise SystemExit(
            f"Missing {p}.\nFetch the official mask archive first:\n"
            "  curl -sL -o data/raw/01_Train_Val_Oil_Spill_mask.7z \\\n"
            "    https://zenodo.org/api/records/8346860/files/01_Train_Val_Oil_Spill_mask.7z/content\n"
            "then extract it to data/raw/masks/."
        )
    raw = np.array(Image.open(p)) > 0
    m = place_mask(raw)
    b.add(Source(
        name=f"Zenodo Sentinel-1 oil-spill mask {MASK_ID}.tif (Part I)",
        kind="sar", real=True,
        source_url="https://zenodo.org/records/8346860",
        licence="CC BY 4.0",
        note=f"Official problem-statement dataset. Real slick morphology, scaled to a "
             f"{SLICK_LENGTH_KM:.0f} km trail and positioned in the case bbox (the mask "
             f"carries shape, not georeferencing). Used both to render the scene and to "
             f"score detection IoU.",
    ))
    return m


def make_lookalikes(b: Build, oil: np.ndarray, n: int = 2) -> list[np.ndarray]:
    """Synthesise look-alike patches.

    The official look-alike MASKS are all-zero by design: they mark oil, and a
    look-alike scene contains none. The look-alike geometry exists only inside
    the 23 GB image archive. So these patches are generated, not real, and
    labelled as such.

    They are deliberately compact and soft-edged: that is what separates a
    low-wind zone or biogenic slick from a mineral-oil discharge, and it is the
    discrimination Stage 2 has to make rather than simply thresholding dark
    pixels.
    """
    rng = np.random.default_rng(SEED + 1)
    yy, xx = np.mgrid[0:GRID, 0:GRID].astype(np.float32)
    out: list[np.ndarray] = []

    # Placed away from the slick so overlap does not confuse the IoU scoring.
    spots = [(0.24, 0.68, 62.0), (0.78, 0.74, 46.0)][:n]
    for i, (fx, fy, r_px) in enumerate(spots):
        cx, cy = fx * GRID, fy * GRID
        # Irregular radius: a few low-order harmonics, so the blob is organic
        # but still far rounder than a discharge trail.
        ang = np.arctan2(yy - cy, xx - cx)
        wob = 1.0
        for k in (2, 3, 5):
            wob = wob + rng.uniform(0.08, 0.20) * np.sin(k * ang + rng.uniform(0, 6.28))
        blob = np.hypot(xx - cx, yy - cy) < r_px * wob
        blob &= ~oil
        out.append(blob)

    b.add(Source(
        name=f"Synthesised look-alike patches ({len(out)})",
        kind="sar", real=False,
        note="The official look-alike masks are empty by construction, so these compact, "
             "soft-edged patches are generated to force the detector to discriminate "
             "rather than threshold. Replaced by real look-alikes once the 23 GB image "
             "archive is available.",
    ))
    return out


# ---------------------------------------------------------------------------
# 2. SAR scene
# ---------------------------------------------------------------------------

def render_sar(b: Build, oil: np.ndarray, lookalikes: list[np.ndarray]) -> np.ndarray:
    """Render a Sentinel-1-like VV backscatter scene in dB.

    Real imagery (Part II, 9.9 GB) is downloading in the background; when it
    lands this is replaced by the actual GeoTIFF. Until then the scene is
    synthesised with the physics that matters for detection:

      - sea clutter as gamma-distributed multi-look speckle, not gaussian noise
      - oil damps Bragg resonance, so it is DARKER with LOWER variance
      - look-alikes are darker but damp variance far less (the real signal that
        separates a biogenic/low-wind patch from mineral oil)
      - a wind-streak gradient, so a global threshold alone is not sufficient
      - bright point targets for vessels

    The detector never sees the mask, so recovering the slick from this scene is
    a genuine test of the thresholding/morphology chain, though it is NOT
    evidence the detector generalises to real SAR. Labelled synthetic.
    """
    real = RAW / "sar_scene.tif"
    if real.exists():
        import rasterio
        with rasterio.open(real) as ds:
            arr = ds.read(1).astype(np.float32)
        b.add(Source(name="Sentinel-1 GRD VV scene", kind="sar", real=True,
                     source_url="https://zenodo.org/records/13761290",
                     licence="CC BY 4.0", note="Real SAR backscatter."))
        return arr

    rng = np.random.default_rng(SEED)
    looks = 4  # Sentinel-1 IW GRD is roughly 4-5 looks

    # Wind-streak field: large-scale modulation of sea roughness.
    yy, xx = np.mgrid[0:GRID, 0:GRID] / GRID
    streaks = (
        0.9
        + 0.16 * np.sin(2 * np.pi * (1.6 * xx + 0.9 * yy))
        + 0.09 * np.sin(2 * np.pi * (4.1 * xx - 2.3 * yy) + 1.2)
        + 0.35 * (0.5 - yy)  # incidence-angle brightness ramp across the swath
    )

    sigma0 = np.clip(streaks, 0.35, None).astype(np.float32)

    # Damping. Oil suppresses capillary waves strongly; look-alikes weakly.
    sigma0[oil] *= 0.16
    for la in lookalikes:
        sigma0[la] *= 0.42

    # Multi-look speckle is multiplicative and gamma-distributed.
    speckle = rng.gamma(shape=looks, scale=1.0 / looks, size=(GRID, GRID)).astype(np.float32)
    # Oil also reduces speckle variance: fewer scatterers in the damped patch.
    speckle[oil] = 1.0 + (speckle[oil] - 1.0) * 0.45

    img = sigma0 * speckle

    # Vessels: bright point targets with a short wake smear.
    for (r, c) in [(190, 300), (700, 820), (410, 640), (880, 210)]:
        img[r - 1:r + 2, c - 1:c + 2] += rng.uniform(6, 11)
        img[r, c:c + 14] += np.linspace(3.0, 0.0, 14)

    db = 10.0 * np.log10(np.clip(img, 1e-4, None)) - 12.0   # into a realistic dB range

    b.add(Source(
        name="Synthesised Sentinel-1-like VV backscatter",
        kind="sar", real=False,
        note="Rendered from the REAL Zenodo oil mask with gamma multi-look speckle, "
             "Bragg damping and wind streaks. Stands in until the 9.9 GB official test "
             "imagery finishes downloading. Slick geometry is real; pixel radiometry is not.",
    ))
    return db.astype(np.float32)


# ---------------------------------------------------------------------------
# 3. Slick geometry and the ground-truth origin
# ---------------------------------------------------------------------------

def slick_geometry(oil: np.ndarray) -> dict:
    """Principal axis of the trail, its endpoints, centroid and area."""
    ys, xs = np.nonzero(oil)
    lon, lat = pixel_to_lonlat(xs.astype(float), ys.astype(float))

    cx, cy = xs.mean(), ys.mean()
    c = np.cov(np.vstack([xs, ys]))
    evals, evecs = np.linalg.eigh(c)
    major = evecs[:, int(np.argmax(evals))]          # (dx, dy) in pixel space

    # Project onto the major axis to find the two ends of the trail.
    t = (xs - cx) * major[0] + (ys - cy) * major[1]
    lo, hi = int(np.argmin(t)), int(np.argmax(t))

    clon, clat = pixel_to_lonlat(np.array([cx]), np.array([cy]))
    end_a = pixel_to_lonlat(np.array([float(xs[lo])]), np.array([float(ys[lo])]))
    end_b = pixel_to_lonlat(np.array([float(xs[hi])]), np.array([float(ys[hi])]))

    # Pixel area in km^2
    b = config.CASE_BBOX
    w_km = (b["east"] - b["west"]) * km_per_deg_lon(config.CASE_CENTER[1])
    h_km = (b["north"] - b["south"]) * KM_PER_DEG_LAT
    px_km2 = (w_km / GRID) * (h_km / GRID)

    # Bearing of the major axis: dy is negative-north in pixel space.
    bearing = (math.degrees(math.atan2(major[0], -major[1]))) % 180.0

    return {
        "centroid": [float(clon[0]), float(clat[0])],
        "end_a": [float(end_a[0][0]), float(end_a[1][0])],
        "end_b": [float(end_b[0][0]), float(end_b[1][0])],
        "area_km2": float(oil.sum() * px_km2),
        "orientation_deg": float(bearing),
        "bounds": [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())],
    }


def drift_vector_km(hours: float) -> tuple[float, float]:
    """Net displacement of surface oil over `hours`, in km."""
    u = MEAN_CURRENT_MS[0] + WIND_FACTOR * MEAN_WIND_MS[0]
    v = MEAN_CURRENT_MS[1] + WIND_FACTOR * MEAN_WIND_MS[1]
    return (u * hours * 3.6, v * hours * 3.6)   # m/s * h * 3.6 -> km


# ---------------------------------------------------------------------------
# 4. Forcing fields
# ---------------------------------------------------------------------------

def build_forcing(b: Build) -> dict:
    """Wind and current fields on a coarse grid over the case bbox.

    Real ERA5/CMEMS need free accounts (cdsapi / copernicusmarine). If the
    NetCDFs are present we use them; otherwise we synthesise a steady field with
    a realistic mesoscale eddy so the drift ensemble has genuine spatial shear
    to work with rather than uniform translation.
    """
    have_wind = (RAW / "era5_wind.nc").exists()
    have_cur = (RAW / "cmems_currents.nc").exists()
    if have_wind and have_cur:
        b.add(Source(name="ERA5 10 m wind", kind="wind", real=True,
                     source_url="https://cds.climate.copernicus.eu/", licence="Copernicus"))
        b.add(Source(name="CMEMS surface currents", kind="current", real=True,
                     source_url="https://marine.copernicus.eu/", licence="Copernicus"))
        return {"mode": "reanalysis", "wind_nc": "era5_wind.nc", "current_nc": "cmems_currents.nc"}

    nx = ny = 32
    bb = config.CASE_BBOX
    lons = np.linspace(bb["west"], bb["east"], nx)
    lats = np.linspace(bb["south"], bb["north"], ny)
    LON, LAT = np.meshgrid(lons, lats)

    # Mean flow plus one anticyclonic eddy — enough shear that the hindcast
    # ensemble spreads realistically instead of translating as a rigid blob.
    ec_lon, ec_lat = -90.05, 28.42
    dx = (LON - ec_lon) * km_per_deg_lon(28.5)
    dy = (LAT - ec_lat) * KM_PER_DEG_LAT
    r = np.hypot(dx, dy) + 1e-6
    amp = 0.09 * np.exp(-(r / 22.0) ** 2)
    u_cur = MEAN_CURRENT_MS[0] - amp * dy / r
    v_cur = MEAN_CURRENT_MS[1] + amp * dx / r

    u_wind = np.full_like(LON, MEAN_WIND_MS[0]) + 0.35 * np.sin(np.radians(LAT * 40))
    v_wind = np.full_like(LON, MEAN_WIND_MS[1]) + 0.35 * np.cos(np.radians(LON * 40))

    np.savez_compressed(
        CASE / "forcing.npz",
        lons=lons, lats=lats,
        u_current=u_cur.astype(np.float32), v_current=v_cur.astype(np.float32),
        u_wind=u_wind.astype(np.float32), v_wind=v_wind.astype(np.float32),
    )
    b.add(Source(
        name="Synthesised wind + surface current field",
        kind="current", real=False,
        note="ERA5 and CMEMS both require free accounts that are not configured. Steady "
             "mean flow plus a 22 km anticyclonic eddy, giving the drift ensemble real "
             "spatial shear. Replace by placing era5_wind.nc and cmems_currents.nc in "
             "data/raw/ and re-running.",
    ))
    return {
        "mode": "synthetic",
        "file": "forcing.npz",
        "mean_current_ms": list(MEAN_CURRENT_MS),
        "mean_wind_ms": list(MEAN_WIND_MS),
        "eddy": {"center": [ec_lon, ec_lat], "radius_km": 22.0, "amplitude_ms": 0.09},
    }


# ---------------------------------------------------------------------------
# 5. AIS
# ---------------------------------------------------------------------------

def load_ais(b: Build) -> "object | None":
    """Clip the NOAA AccessAIS day file to the case bbox and time window."""
    import pandas as pd

    z = RAW / "AIS_2023_06_15.zip"
    if not z.exists():
        b.add(Source(name="NOAA AccessAIS", kind="ais", real=False,
                     note="Day file not downloaded; only the synthetic polluter is present."))
        return None

    bb = config.CASE_BBOX
    with zipfile.ZipFile(z) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        chunks = []
        for ch in pd.read_csv(zf.open(name), chunksize=500_000,
                              usecols=["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG",
                                       "VesselName", "VesselType"]):
            m = ((ch.LON >= bb["west"]) & (ch.LON <= bb["east"])
                 & (ch.LAT >= bb["south"]) & (ch.LAT <= bb["north"]))
            if m.any():
                chunks.append(ch[m])

    if not chunks:
        b.add(Source(name="NOAA AccessAIS", kind="ais", real=False,
                     note="No AIS records fall inside the case bbox."))
        return None

    df = pd.concat(chunks, ignore_index=True)
    df["BaseDateTime"] = pd.to_datetime(df.BaseDateTime, utc=True)
    df = df.sort_values(["MMSI", "BaseDateTime"]).reset_index(drop=True)

    b.add(Source(
        name=f"NOAA AccessAIS 2023-06-15 ({df.MMSI.nunique()} vessels, {len(df):,} positions)",
        kind="ais", real=True,
        source_url="https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2023/",
        licence="Public domain (US Government)",
        note="Official problem-statement source. Clipped to the case bbox.",
    ))
    return df


def inject_polluter(b: Build, geom: dict, origin: list[float]):
    """Add the ground-truth polluter.

    It transits along the slick's own axis (a discharge laid down while
    underway), passes through the origin at the origin time, and goes AIS-dark
    across that window. This is the known answer Stage 3 must recover.
    """
    import pandas as pd

    lon0, lat0 = origin
    # Course along the trail axis, pointing from end_a toward end_b.
    ax = geom["end_b"][0] - geom["end_a"][0]
    ay = geom["end_b"][1] - geom["end_a"][1]
    course = math.degrees(math.atan2(ax * km_per_deg_lon(lat0), ay * KM_PER_DEG_LAT)) % 360.0

    speed_kn = 11.5
    speed_kmh = speed_kn * 1.852
    rows = []
    # 6 hours either side of the origin time, 2-minute reporting.
    for i in range(-180, 181):
        t = ORIGIN_TIME + timedelta(minutes=2 * i)
        along = speed_kmh * (2 * i) / 60.0
        lon, lat = offset_km(lon0, lat0,
                             along * math.sin(math.radians(course)),
                             along * math.cos(math.radians(course)))
        # The gap: transmissions stop across the release window.
        if abs(2 * i) <= POLLUTER_GAP_MINUTES / 2:
            continue
        rows.append({
            "MMSI": POLLUTER_MMSI, "BaseDateTime": t, "LAT": round(lat, 6), "LON": round(lon, 6),
            "SOG": speed_kn, "COG": round(course, 1),
            "VesselName": POLLUTER_NAME, "VesselType": 80,
        })

    b.add(Source(
        name=f"Injected ground-truth polluter ({POLLUTER_NAME})",
        kind="synthetic", real=False,
        note=f"One synthetic vessel transiting the slick axis on course {course:.0f}deg, "
             f"AIS-dark for {POLLUTER_GAP_MINUTES:.0f} min across the release window. "
             "This is the known answer used to validate Stage 3.",
    ))
    return pd.DataFrame(rows), course


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    CASE.mkdir(parents=True, exist_ok=True)
    b = Build()
    print(f"Building case {config.CASE_ID}\n")

    print("Imagery")
    oil = load_oil_mask(b)
    looks = make_lookalikes(b, oil)
    sar = render_sar(b, oil, looks)

    geom = slick_geometry(oil)

    # Ground-truth origin: the upstream end of the trail, wound back by the
    # drift the slick has undergone since release.
    dx, dy = drift_vector_km(DRIFT_HOURS)
    # end_a is the older end if it lies up-drift; pick whichever is further
    # against the drift direction.
    def updrift(p):
        return -(p[0] - geom["centroid"][0]) * dx - (p[1] - geom["centroid"][1]) * dy
    older = geom["end_a"] if updrift(geom["end_a"]) > updrift(geom["end_b"]) else geom["end_b"]
    origin = list(offset_km(older[0], older[1], -dx, -dy))

    print("\nForcing")
    forcing = build_forcing(b)

    print("\nAIS")
    ais = load_ais(b)
    polluter, course = inject_polluter(b, geom, origin)

    import pandas as pd
    combined = pd.concat([ais, polluter], ignore_index=True) if ais is not None else polluter
    # The real feed types MMSI as int64 and VesselType is sparsely populated;
    # normalise both so the injected vessel and the real ones share a schema.
    combined["MMSI"] = combined.MMSI.astype("int64").astype(str)
    combined["VesselType"] = pd.to_numeric(combined.VesselType, errors="coerce").fillna(0).astype("int32")
    combined["VesselName"] = combined.VesselName.fillna("").astype(str)
    for c in ("LAT", "LON", "SOG", "COG"):
        combined[c] = pd.to_numeric(combined[c], errors="coerce").astype("float32")
    combined = combined.sort_values(["MMSI", "BaseDateTime"]).reset_index(drop=True)
    combined.to_parquet(CASE / "ais.parquet", index=False)

    np.save(CASE / "sar_db.npy", sar)
    np.save(CASE / "mask_oil.npy", oil)
    if looks:
        np.save(CASE / "mask_lookalike.npy", np.any(np.stack(looks), axis=0))

    meta = {
        "id": config.CASE_ID,
        "name": config.CASE_NAME,
        "bbox": config.CASE_BBOX,
        "center": list(config.CASE_CENTER),
        "grid": GRID,
        "scene_id": config.SCENE_ID,
        "acquired_at": ACQUIRED.isoformat(),
        "seed": SEED,
        "disclaimer": config.DISCLAIMER,
        "sources": [s.as_dict() for s in b.sources],
        "forcing": forcing,
        "slick": geom,
        "ground_truth": {
            "origin": [round(origin[0], 6), round(origin[1], 6)],
            "origin_time_utc": ORIGIN_TIME.isoformat(),
            "drift_hours": DRIFT_HOURS,
            "drift_km": [round(dx, 3), round(dy, 3)],
            "polluter_mmsi": POLLUTER_MMSI,
            "polluter_name": POLLUTER_NAME,
            "polluter_type": POLLUTER_TYPE,
            "polluter_course_deg": round(course, 1),
            "polluter_gap_minutes": POLLUTER_GAP_MINUTES,
            "note": "Stage 2 must place this origin inside its 90% cone; Stage 3 must "
                    "rank this MMSI first. Both are Phase acceptance criteria.",
        },
        "files": {
            "sar_db": "sar_db.npy",
            "mask_oil": "mask_oil.npy",
            "mask_lookalike": "mask_lookalike.npy" if looks else None,
            "ais": "ais.parquet",
            "forcing": forcing.get("file"),
        },
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    (CASE / "case.json").write_text(json.dumps(meta, indent=2))

    real = sum(s.real for s in b.sources)
    print(f"\nWrote {CASE}/case.json")
    print(f"  sources        {real} real, {len(b.sources) - real} synthesised")
    print(f"  slick area     {geom['area_km2']:.1f} km2, bearing {geom['orientation_deg']:.0f} deg")
    print(f"  origin         {origin[0]:.4f}, {origin[1]:.4f} @ {ORIGIN_TIME:%Y-%m-%d %H:%M}Z")
    print(f"  drift          {dx:+.1f}, {dy:+.1f} km over {DRIFT_HOURS:.0f} h")
    print(f"  AIS            {combined.MMSI.nunique()} vessels, {len(combined):,} positions")


if __name__ == "__main__":
    main()
