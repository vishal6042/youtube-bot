"""Country flag images for bar races.

Resolves a country label (as it appears in World Bank / OWID data) to an ISO
alpha-2 code, downloads the flag once from flagcdn.com (free, no key), and
caches it under data/flags/ as a numpy image ready for matplotlib.

Windows cannot render flag emoji in matplotlib (Segoe UI Emoji draws regional
indicator letters, not flags), so real images are the only reliable option.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
import requests

from .config import PROJECT_ROOT

_CACHE_DIR = PROJECT_ROOT / "data" / "flags"
_MEM: dict[str, Any] = {}
_MISSING: set[str] = set()

# Names that pycountry can't match (World Bank / OWID phrasing).
_ALIASES = {
    "united states": "US", "united states of america": "US",
    "united kingdom": "GB",
    "united kingdom of great britain and northern ireland": "GB",
    "russia": "RU", "russian federation": "RU",
    "south korea": "KR", "korea, rep.": "KR", "korea (republic of)": "KR",
    "north korea": "KP", "korea, dem. people's rep.": "KP",
    "iran": "IR", "iran, islamic rep.": "IR",
    "egypt": "EG", "egypt, arab rep.": "EG",
    "venezuela": "VE", "venezuela, rb": "VE",
    "vietnam": "VN", "viet nam": "VN",
    "syria": "SY", "syrian arab republic": "SY",
    "turkey": "TR", "turkiye": "TR", "türkiye": "TR",
    "czechia": "CZ", "czech republic": "CZ",
    "slovakia": "SK", "slovak republic": "SK",
    "laos": "LA", "lao pdr": "LA",
    "congo, dem. rep.": "CD", "democratic republic of congo": "CD",
    "congo, rep.": "CG", "congo": "CG",
    "hong kong": "HK", "hong kong sar, china": "HK",
    "macao": "MO", "macao sar, china": "MO",
    "taiwan": "TW", "taiwan, province of china": "TW",
    "bolivia": "BO", "brunei": "BN", "brunei darussalam": "BN",
    "cape verde": "CV", "cabo verde": "CV",
    "ivory coast": "CI", "cote d'ivoire": "CI", "côte d'ivoire": "CI",
    "kyrgyzstan": "KG", "kyrgyz republic": "KG",
    "moldova": "MD", "republic of moldova": "MD",
    "tanzania": "TZ", "united republic of tanzania": "TZ",
    "gambia": "GM", "gambia, the": "GM",
    "bahamas": "BS", "bahamas, the": "BS",
    "yemen": "YE", "yemen, rep.": "YE",
    "st. lucia": "LC", "saint lucia": "LC",
    "micronesia": "FM", "micronesia, fed. sts.": "FM",
    "sint maarten (dutch part)": "SX",
    "new caledonia": "NC",
    # Cricket teams. England and Scotland are not ISO countries, and fuzzy
    # matching finds the wrong thing rather than nothing, so pin them to GB.
    # West Indies and the XI sides are multi-nation squads with no flag —
    # deliberately unmapped, `flag_image` returns None and the bar just has
    # no flag beside it.
    "england": "GB", "scotland": "GB",
}


def iso2(name: str) -> str | None:
    """Best-effort ISO alpha-2 code for a country label."""
    key = str(name).strip().lower()
    if key in _ALIASES:
        return _ALIASES[key]
    try:
        import pycountry

        found = pycountry.countries.get(name=str(name).strip())
        if found:
            return found.alpha_2
        matches = pycountry.countries.search_fuzzy(str(name))
        if matches:
            return matches[0].alpha_2
    except Exception:
        pass
    return None


def _download(code: str) -> bytes | None:
    try:
        resp = requests.get(f"https://flagcdn.com/w80/{code.lower()}.png", timeout=20)
        if resp.status_code == 200 and resp.content:
            return resp.content
    except Exception:
        pass
    return None


def flag_image(name: str):
    """RGBA numpy array for a country's flag, or None if unavailable."""
    if name in _MEM:
        return _MEM[name]
    if name in _MISSING:
        return None

    code = iso2(name)
    if not code:
        _MISSING.add(name)
        return None

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _CACHE_DIR / f"{code.lower()}.png"
    if not path.exists():
        data = _download(code)
        if not data:
            _MISSING.add(name)
            return None
        path.write_bytes(data)

    try:
        import matplotlib.image as mpimg

        img = mpimg.imread(io.BytesIO(path.read_bytes()), format="png")
        _MEM[name] = img
        return img
    except Exception:
        _MISSING.add(name)
        return None


def preload(names: list[str]) -> dict[str, Any]:
    """Fetch every flag up front so rendering never blocks on the network."""
    out: dict[str, Any] = {}
    for n in names:
        img = flag_image(n)
        if img is not None:
            out[n] = img
    return out
