"""ML Basics #6 — Classification vs regression: category or number?"""
from __future__ import annotations

import numpy as np
from manim import BOLD, Axes, Create, FadeIn, FadeOut, Line, VGroup, Write
from manim import Dot as MDot

from graph_bot.scenes._base import (
    ACCENT,
    BLUE,
    GOLD,
    GRID,
    MUTED,
    PINK,
    VoiceBrandScene,
    brand_text,
)
from graph_bot.scenes.components import column_header

RNG = np.random.default_rng(3)


class ClassificationVsRegression(VoiceBrandScene):
    SERIES = "ML BASICS #6"
    TITLE = "Classification vs Regression"
    SOURCE = "Concept explainer"

    def body(self) -> None:
        # ---------------- classification ----------------
        head1 = column_header("CLASSIFICATION", ACCENT, 0, 4.8, size=29)
        sub1 = brand_text("predicts a category", size=23, color=MUTED)
        sub1.move_to([0, 4.2, 0])

        blue_pts = RNG.normal([-1.25, 2.4], 0.5, size=(8, 2))
        pink_pts = RNG.normal([1.25, 1.3], 0.5, size=(8, 2))
        dots1 = VGroup(
            *[MDot([x, y, 0], color=BLUE, radius=0.1) for x, y in blue_pts],
            *[MDot([x, y, 0], color=PINK, radius=0.1) for x, y in pink_pts],
        )
        boundary = Line([-3.0, 0.9, 0], [3.0, 2.9, 0], color=GOLD, stroke_width=6)

        with self.voiceover(
            text="Classification predicts a category. Spam or not spam. Cat or dog."
        ) as t:
            self.play(FadeIn(head1), FadeIn(sub1), run_time=t.duration * 0.35)
            self.play(FadeIn(dots1, lag_ratio=0.05), run_time=t.duration * 0.65)

        with self.voiceover(
            text="The model draws a boundary, and whichever side you land on is your answer."
        ) as t:
            self.play(Create(boundary), run_time=t.duration * 0.6)
            self.wait(t.duration * 0.4)

        top = VGroup(head1, sub1, dots1, boundary)
        self.play(top.animate.scale(0.72).shift([0, 0.9, 0]), run_time=0.6)

        # ---------------- regression ----------------
        head2 = column_header("REGRESSION", GOLD, 0, -0.5, size=29)
        sub2 = brand_text("predicts a number", size=23, color=MUTED)
        sub2.move_to([0, -1.1, 0])

        ax = Axes(
            x_range=[0, 10, 1], y_range=[0, 10, 1],
            x_length=5.6, y_length=3.0, tips=False,
            axis_config={"color": GRID, "stroke_width": 3, "include_ticks": False},
        )
        ax.move_to([0, -3.2, 0])
        xs = np.linspace(1, 9, 9)
        ys = 0.75 * xs + 1.2 + RNG.normal(0, 0.6, xs.size)
        dots2 = VGroup(*[MDot(ax.c2p(x, y), color=MUTED, radius=0.09)
                         for x, y in zip(xs, ys)])
        fit = ax.plot(lambda x: 0.75 * x + 1.2, x_range=[0.6, 9.4],
                      color=ACCENT, stroke_width=6)

        with self.voiceover(
            text="Regression predicts a number instead. A house price. Tomorrow's temperature."
        ) as t:
            self.play(FadeIn(head2), FadeIn(sub2), run_time=t.duration * 0.3)
            self.play(Create(ax), FadeIn(dots2, lag_ratio=0.05), run_time=t.duration * 0.7)

        with self.voiceover(
            text="So instead of a boundary, it fits a line through the data."
        ) as t:
            self.play(Create(fit), run_time=t.duration * 0.7)
            self.wait(t.duration * 0.3)

        punch = brand_text("Category → classify.  Number → regress.",
                           size=26, weight=BOLD, color=ACCENT)
        punch.move_to([0, -5.2, 0])
        if punch.width > 8.3:
            punch.scale_to_fit_width(8.3)
        with self.voiceover(
            text="Predicting a category? Classification. Predicting a number? Regression."
        ) as t:
            self.play(Write(punch), run_time=t.duration * 0.7)
            self.wait(t.duration * 0.3)
        self.wait(0.5)
