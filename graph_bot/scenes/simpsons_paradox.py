"""Simpson's Paradox — a trend that reverses when you split the data."""
from __future__ import annotations

import numpy as np
from manim import (
    BOLD,
    Axes,
    Create,
    FadeIn,
    FadeOut,
    Transform,
    VGroup,
    Write,
)
from manim import Dot as MDot

from graph_bot.scenes._base import (
    ACCENT,
    BLUE,
    FG,
    GOLD,
    GRID,
    MUTED,
    PINK,
    WARN,
    BrandScene,
    brand_text,
)


def _group(x0: float, x1: float, y0: float, slope: float, n: int, seed: int):
    """Points on a downward line inside a band, with a little noise."""
    rng = np.random.default_rng(seed)
    xs = np.linspace(x0, x1, n) + rng.normal(0, 0.10, n)
    ys = y0 + slope * (xs - x0) + rng.normal(0, 0.28, n)
    return xs, ys


class SimpsonsParadox(BrandScene):
    TITLE = "The Trend That Lies"
    SUBTITLE = "Simpson's Paradox"
    SOURCE = "Concept explainer"

    def body(self) -> None:
        ax = Axes(
            x_range=[0, 10, 1], y_range=[0, 10, 1],
            x_length=7.0, y_length=6.6, tips=False,
            axis_config={"color": GRID, "stroke_width": 3, "include_ticks": False},
        )
        ax.move_to([0, 0.5, 0])
        self.play(Create(ax), run_time=0.7)

        # Two groups: each slopes DOWN, but the second sits higher and further right.
        ax_x, ay = _group(1.2, 4.3, 4.6, -0.35, 14, seed=1)
        bx, by = _group(5.6, 8.8, 8.2, -0.35, 14, seed=2)

        all_dots = VGroup(*[
            MDot(ax.c2p(x, y), color=MUTED, radius=0.085)
            for x, y in zip(np.concatenate([ax_x, bx]), np.concatenate([ay, by]))
        ])
        self.play(FadeIn(all_dots, lag_ratio=0.04), run_time=1.4)

        cap = self.caption("Overall, the trend goes UP ↗")
        self.play(Write(cap), run_time=0.8)

        # Overall (misleading) trend line.
        allx = np.concatenate([ax_x, bx])
        ally = np.concatenate([ay, by])
        m, c = np.polyfit(allx, ally, 1)
        overall = ax.plot(lambda x: m * x + c, x_range=[0.8, 9.2],
                          color=GOLD, stroke_width=8)
        self.play(Create(overall), run_time=1.2)
        self.wait(1.0)

        cap2 = self.caption("But split it into two groups…", color=FG)
        self.play(Transform(cap, cap2), run_time=0.7)
        self.play(FadeOut(overall), run_time=0.5)

        # Recolour into the two hidden groups.
        n_a = len(ax_x)
        self.play(
            *[d.animate.set_color(BLUE) for d in all_dots[:n_a]],
            *[d.animate.set_color(PINK) for d in all_dots[n_a:]],
            run_time=1.0,
        )

        ma, ca = np.polyfit(ax_x, ay, 1)
        mb, cb = np.polyfit(bx, by, 1)
        line_a = ax.plot(lambda x: ma * x + ca, x_range=[1.0, 4.5], color=BLUE, stroke_width=8)
        line_b = ax.plot(lambda x: mb * x + cb, x_range=[5.4, 9.0], color=PINK, stroke_width=8)
        self.play(Create(line_a), Create(line_b), run_time=1.3)

        cap3 = self.caption("…each group trends DOWN ↘", color=WARN)
        self.play(Transform(cap, cap3), run_time=0.8)
        self.wait(1.6)

        self.play(FadeOut(cap), run_time=0.4)
        punch = brand_text("Same data. Opposite conclusion.", size=31, weight=BOLD, color=ACCENT)
        punch.move_to([0, -5.9, 0])
        self.play(Write(punch), run_time=1.1)
        self.wait(1.8)
