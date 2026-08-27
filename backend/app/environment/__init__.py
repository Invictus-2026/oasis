"""
Phase 3 — normalised environmental data.

The simulation engine should not know or care whether its forcing came from a
frozen case bundle, a CMEMS/ERA5 download, an INCOIS feed, or a synthetic
fallback. Everything here exists to make that true: one shared
`EnvironmentalData` type, one `EnvironmentalDataProvider` interface, and a
resolver that picks the best available implementation and degrades to a mock
rather than failing.

    EnvironmentalDataProvider   the seam (base.py)
    CaseBundleProvider          real data from the frozen case (bundle.py)
    MockEnvironmentalProvider   synthetic fallback, always available (mock.py)
    get_provider()              resolution + fallback policy (resolver.py)
"""

from app.environment.base import EnvironmentalData, EnvironmentalDataProvider
from app.environment.bundle import CaseBundleProvider
from app.environment.mock import MockEnvironmentalProvider
from app.environment.resolver import get_provider, list_providers

__all__ = [
    "EnvironmentalData",
    "EnvironmentalDataProvider",
    "CaseBundleProvider",
    "MockEnvironmentalProvider",
    "get_provider",
    "list_providers",
]
