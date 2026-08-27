"""Provider resolution and fallback policy.

One place decides which environmental source is used, so callers never branch
on availability themselves. The order is: an explicit mock override, then the
best available real provider, then the synthetic fallback.

Adding a CMEMS/ERA5/INCOIS provider later means implementing
`EnvironmentalDataProvider` and inserting it into `_real_providers()` — no
caller changes anywhere.
"""

from __future__ import annotations

from app.core import config
from app.environment.base import EnvironmentalDataProvider
from app.environment.bundle import CaseBundleProvider
from app.environment.mock import MockEnvironmentalProvider

_MOCK = MockEnvironmentalProvider()


def _forced_mock() -> bool:
    """ENV_DATA_MODE=mock forces the fallback, mirroring the frontend's
    VITE_FORCE_MOCK escape hatch."""
    return str(getattr(config, "ENV_DATA_MODE", "auto")).lower() == "mock"


def _real_providers(bundle) -> list[EnvironmentalDataProvider]:
    """Real sources in preference order.

    Future providers (CMEMS currents, ERA5 wind, INCOIS for the Indian Ocean)
    slot in here ahead of or behind the bundle as appropriate.
    """
    return [CaseBundleProvider(bundle)]


def get_provider(bundle=None) -> EnvironmentalDataProvider:
    """The best environmental provider currently usable.

    Never raises and never returns None: if nothing real is available the
    synthetic provider is returned, which is what keeps the API answering with
    no case bundle, no credentials and no network.
    """
    if _forced_mock():
        return _MOCK

    for provider in _real_providers(bundle):
        if provider.available():
            return provider

    return _MOCK


def list_providers(bundle=None) -> list[dict]:
    """Every known provider and whether it can currently serve data.

    Surfaced through the API so the mock/real distinction is inspectable rather
    than guessed at from the data.
    """
    entries = [
        {"name": p.name, "available": p.available(), "kind": "real"}
        for p in _real_providers(bundle)
    ]
    entries.append({"name": _MOCK.name, "available": True, "kind": "mock"})
    return entries
