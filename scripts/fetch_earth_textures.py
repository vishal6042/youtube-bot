"""Download the NASA Earth images that graph_bot/sims/earth_water.py draws from.

    .venv/Scripts/python.exe scripts/fetch_earth_textures.py

Three public images from NASA's Earth Observatory (Blue Marble Next Generation;
depths and heights from GEBCO), 64 MB in all, into assets/earth/. They are not
committed. See assets/earth/CREDITS.md for the credit line.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

BASE = "https://assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng"
FILES = {
    "world.topo.bathy.200407.3x21600x10800.jpg": f"{BASE}/bmng-topography-bathymetry/july/world.topo.bathy.200407.3x21600x10800.jpg",
    "gebco_08_rev_bath_21600x10800.jpg": f"{BASE}/bathymetry/gebco_08_rev_bath_21600x10800.jpg",
    "gebco_08_rev_elev_21600x10800.jpg": f"{BASE}/topography/gebco_08_rev_elev_21600x10800.jpg",
}
DEST = Path(__file__).resolve().parents[1] / "assets" / "earth"


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        out = DEST / name
        if out.exists() and out.stat().st_size > 1_000_000:
            print("have", name)
            continue
        print("fetching", name)
        urllib.request.urlretrieve(url, out)
        print("  ", round(out.stat().st_size / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
