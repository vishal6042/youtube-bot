"""Render one slice of a simulated Short's frames to its own video file.

Started by kit.encode (one process per slice, so all CPU cores draw at once):

    python -m graph_bot.sims._chunk <module> <first frame> <end frame> <fps> <out.mp4> <ffmpeg> [json kwargs]

Prints "p <frames done>" lines so the parent can report progress.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import numpy as np


def main() -> None:
    mod_name, a, b, fps, out, ffmpeg = sys.argv[1:7]
    kw = json.loads(sys.argv[7]) if len(sys.argv) > 7 else {}
    a, b, fps = int(a), int(b), int(fps)
    from . import canvas as cv

    mod = importlib.import_module(mod_name)
    _, frame, _ = mod.build(ffmpeg, **kw)
    enc = cv.Encoder(Path(out), ffmpeg, fps=fps, threads=2)
    try:
        for i, fi in enumerate(range(a, b)):
            enc.write(np.asarray(frame(fi / fps)))
            if i % 10 == 9:
                print(f"p {i + 1}", flush=True)
    except BaseException:
        enc.proc.kill()
        enc.proc.wait()
        raise
    enc.close()
    print(f"p {b - a}", flush=True)


if __name__ == "__main__":
    main()
