"""Render a simulated Short: python -m graph_bot.sims <name> <out.mp4> [seed]"""
from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

from ..config import load_settings
from ..render import ffmpeg_exe
from . import SIMS


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in SIMS:
        sys.exit(f"usage: python -m graph_bot.sims <{'|'.join(SIMS)}> <out.mp4> [seed]")
    mod = importlib.import_module(SIMS[sys.argv[1]])
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 11
    start = time.time()
    secs = mod.render(Path(sys.argv[2]), ffmpeg_exe(load_settings()), seed=seed,
                      progress=lambda i, n: print(f"\r  frame {i}/{n}", end="", flush=True))
    print(f"\n{sys.argv[2]}: {secs:.1f}s video in {time.time() - start:.0f}s")


if __name__ == "__main__":
    main()
