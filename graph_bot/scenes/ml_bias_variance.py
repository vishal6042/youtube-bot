"""ML Basics #9 — Bias vs variance: too simple, too complex, just right."""
from __future__ import annotations

import numpy as np
from manim import BOLD, Axes, Create, FadeIn, FadeOut, Transform, VGroup, Write
from manim import Dot as MDot

from graph_bot.scenes._base import (
    ACCENT,
    GOLD,
    GRID,
    MUTED,
    PINK,
    VoiceBrandScene,
    brand_text,
)

RNG = np.random.default_rng(33)
XS = np.linspace(1.2, 8.8, 10)
TRUE_M, TRUE_C = 0.7, 1.5
YS = TRUE_M * XS + TRUE_C + RNG.normal(0, 0.7, XS.size)
RESID = YS - (TRUE_M * XS + TRUE_C)


class BiasVariance(VoiceBrandScene):
    SERIES = "ML BASICS #9"
    TITLE = "Bias vs Variance"
    SUBTITLE = "Too simple, too complex, just right"
    SOURCE = "Concept explainer"

    def body(self) -> None:
        ax = Axes(
            x_range=[0, 10, 1], y_range=[0, 10, 1],
            x_length=7.0, y_length=6.0, tips=False,
            axis_config={"color": GRID, "stroke_width": 3, "include_ticks": False},
        )
        ax.move_to([0, 1.0, 0])
        dots = VGroup(*[MDot(ax.c2p(x, y), color=MUTED, radius=0.1)
                        for x, y in zip(XS, YS)])
        self.play(Create(ax), FadeIn(dots, lag_ratio=0.06), run_time=1.2)

        # ---- underfit (high bias) ----
        flat = ax.plot(lambda x: 5.0, x_range=[0.5, 9.5], color=PINK, stroke_width=7)
        cap = self.caption("UNDERFIT — too simple", y=-3.9, size=28, color=PINK)
        tag = brand_text("high bias", size=26, color=PINK, weight=BOLD)
        tag.move_to([0, -4.9, 0])

        with self.voiceover(
            text="If a model is too simple, it cannot capture the pattern at all. "
                 "We call that high bias — it underfits."
        ) as t:
            self.play(Create(flat), run_time=t.duration * 0.45)
            self.play(Write(cap), FadeIn(tag), run_time=t.duration * 0.55)

        # ---- overfit (high variance) ----
        def wiggly(x: float) -> float:
            bumps = RESID * np.exp(-((x - XS) ** 2) / (2 * 0.30**2))
            return float(TRUE_M * x + TRUE_C + bumps.sum())

        wig = ax.plot(wiggly, x_range=[0.6, 9.4, 0.02], color=GOLD, stroke_width=7)
        cap2 = self.caption("OVERFIT — too complex", y=-3.9, size=28, color=GOLD)
        tag2 = brand_text("high variance", size=26, color=GOLD, weight=BOLD)
        tag2.move_to([0, -4.9, 0])

        with self.voiceover(
            text="If it is too complex, it chases every wobble in the training data. "
                 "That is high variance — it overfits."
        ) as t:
            self.play(Transform(flat, wig), Transform(cap, cap2), Transform(tag, tag2),
                      run_time=t.duration * 0.6)
            self.wait(t.duration * 0.4)

        # ---- just right ----
        best = ax.plot(lambda x: TRUE_M * x + TRUE_C, x_range=[0.5, 9.5],
                       color=ACCENT, stroke_width=7)
        cap3 = self.caption("JUST RIGHT — learns the trend ✅", y=-3.9, size=28, color=ACCENT)
        tag3 = brand_text("balanced", size=26, color=ACCENT, weight=BOLD)
        tag3.move_to([0, -4.9, 0])

        with self.voiceover(
            text="The sweet spot sits between them. Complex enough to see the pattern, "
                 "simple enough to ignore the noise."
        ) as t:
            self.play(Transform(flat, best), Transform(cap, cap3), Transform(tag, tag3),
                      run_time=t.duration * 0.6)
            self.wait(t.duration * 0.4)

        self.play(FadeOut(cap), FadeOut(tag), run_time=0.35)
        punch = brand_text("Every model lives on this trade-off.", size=28,
                           weight=BOLD, color=ACCENT)
        punch.move_to([0, -5.2, 0])
        if punch.width > 8.3:
            punch.scale_to_fit_width(8.3)
        with self.voiceover(
            text="Every model you ever train lives somewhere on this trade-off."
        ) as t:
            self.play(Write(punch), run_time=t.duration * 0.7)
            self.wait(t.duration * 0.3)
        self.wait(0.5)
