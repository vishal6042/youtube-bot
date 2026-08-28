"""ML Basics #2 — Overfitting: memorising noise instead of learning the pattern."""
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
    FG,
    GOLD,
    GRID,
    MUTED,
    PINK,
    VoiceBrandScene,
    brand_text,
)

RNG = np.random.default_rng(11)
TRUE_M, TRUE_C = 0.62, 1.6
XS = np.linspace(1.0, 9.0, 11)
YS = TRUE_M * XS + TRUE_C + RNG.normal(0, 0.72, XS.size)


class Overfitting(VoiceBrandScene):
    SERIES = "ML BASICS #2"
    TITLE = "Overfitting"
    SUBTITLE = "Memorising instead of learning"
    SOURCE = "Concept explainer"

    def body(self) -> None:
        ax = Axes(
            x_range=[0, 10, 1], y_range=[0, 10, 1],
            x_length=7.0, y_length=6.4, tips=False,
            axis_config={"color": GRID, "stroke_width": 3, "include_ticks": False},
        )
        ax.move_to([0, 0.7, 0])

        dots = VGroup(*[MDot(ax.c2p(x, y), color=MUTED, radius=0.095)
                        for x, y in zip(XS, YS)])

        with self.voiceover(
            text="Here is some training data. Our goal is to find the pattern inside it."
        ) as t:
            self.play(Create(ax), run_time=t.duration * 0.35)
            self.play(FadeIn(dots, lag_ratio=0.06), run_time=t.duration * 0.65)

        # ---- good fit ----
        good = ax.plot(lambda x: TRUE_M * x + TRUE_C, x_range=[0.6, 9.4],
                       color=ACCENT, stroke_width=8)
        cap = self.caption("A simple model: learns the trend ✅", y=-4.9, size=28)

        with self.voiceover(
            text="A simple model draws a straight line through it. "
                 "It misses a few points, and that is fine."
        ) as t:
            self.play(Create(good), run_time=t.duration * 0.6)
            self.play(Write(cap), run_time=t.duration * 0.4)
        self.wait(0.4)

        # ---- overfit ----
        # A wiggly curve that hits every training point. Built from Gaussian bumps
        # on top of the true line rather than a high-degree polyfit, which would
        # blow up at the edges (Runge phenomenon) and look like a render glitch.
        residuals = YS - (TRUE_M * XS + TRUE_C)
        width = 0.30

        def wiggly(x: float) -> float:
            bumps = residuals * np.exp(-((x - XS) ** 2) / (2 * width**2))
            return float(TRUE_M * x + TRUE_C + bumps.sum())

        over = ax.plot(wiggly, x_range=[0.6, 9.4, 0.02], color=PINK, stroke_width=8)
        cap2 = self.caption("A complex model: hits every point 🤔", y=-4.9, size=28, color=GOLD)

        with self.voiceover(
            text="Now watch a much more complex model. It bends and twists to pass "
                 "through every single training point. Perfect score."
        ) as t:
            self.play(FadeOut(good), Transform(cap, cap2), run_time=t.duration * 0.3)
            self.play(Create(over), run_time=t.duration * 0.7)

        # ---- new data exposes the problem ----
        new_x = np.array([2.6, 5.4, 7.9])
        new_y = TRUE_M * new_x + TRUE_C + np.array([0.35, -0.4, 0.3])
        new_dots = VGroup(*[MDot(ax.c2p(x, y), color=GOLD, radius=0.12)
                            for x, y in zip(new_x, new_y)])

        cap3 = self.caption("But on NEW data it fails ❌", y=-4.9, size=29, color=PINK)
        with self.voiceover(
            text="But then new data arrives. The twisted model is nowhere near it. "
                 "It memorised the noise instead of learning the pattern."
        ) as t:
            self.play(FadeIn(new_dots, scale=1.5), run_time=t.duration * 0.35)
            self.play(Transform(cap, cap3), run_time=t.duration * 0.25)
            self.play(FadeIn(good), run_time=t.duration * 0.4)

        self.play(FadeOut(cap), run_time=0.35)
        punch = brand_text("Simpler often generalises better.", size=30,
                           weight=BOLD, color=ACCENT)
        punch.move_to([0, -5.1, 0])
        with self.voiceover(
            text="That is overfitting. Simpler models often work better on data "
                 "they have never seen."
        ) as t:
            self.play(Write(punch), run_time=t.duration * 0.55)
            self.wait(t.duration * 0.45)
        self.wait(0.5)
