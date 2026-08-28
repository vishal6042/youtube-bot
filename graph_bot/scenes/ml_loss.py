"""ML Basics #7 — The loss function: one number that says 'how wrong'."""
from __future__ import annotations

import numpy as np
from manim import (
    BOLD,
    Axes,
    Create,
    DashedLine,
    FadeIn,
    FadeOut,
    Transform,
    VGroup,
    Write,
)
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

RNG = np.random.default_rng(21)
XS = np.linspace(1.2, 8.8, 8)
YS = 0.72 * XS + 1.4 + RNG.normal(0, 0.7, XS.size)


class LossFunction(VoiceBrandScene):
    SERIES = "ML BASICS #7"
    TITLE = "The Loss Function"
    SUBTITLE = "One number for 'how wrong'"
    SOURCE = "Concept explainer"

    def body(self) -> None:
        ax = Axes(
            x_range=[0, 10, 1], y_range=[0, 10, 1],
            x_length=7.0, y_length=6.2, tips=False,
            axis_config={"color": GRID, "stroke_width": 3, "include_ticks": False},
        )
        ax.move_to([0, 0.9, 0])
        dots = VGroup(*[MDot(ax.c2p(x, y), color=MUTED, radius=0.1)
                        for x, y in zip(XS, YS)])

        with self.voiceover(
            text="How does a model know it is wrong? We measure it."
        ) as t:
            self.play(Create(ax), run_time=t.duration * 0.4)
            self.play(FadeIn(dots, lag_ratio=0.07), run_time=t.duration * 0.6)

        # A deliberately bad first guess.
        bad_m, bad_c = 0.25, 4.6
        bad = ax.plot(lambda x: bad_m * x + bad_c, x_range=[0.5, 9.5],
                      color=PINK, stroke_width=7)

        with self.voiceover(
            text="Here is the model's first guess. Clearly not great."
        ) as t:
            self.play(Create(bad), run_time=t.duration * 0.6)
            self.wait(t.duration * 0.4)

        errors = VGroup(*[
            DashedLine(ax.c2p(x, y), ax.c2p(x, bad_m * x + bad_c),
                       color=GOLD, stroke_width=5, dash_length=0.12)
            for x, y in zip(XS, YS)
        ])

        cap = self.caption("Add up every error → the loss", y=-3.6, size=27, color=GOLD)
        with self.voiceover(
            text="For each point, measure the gap between the prediction and the truth. "
                 "Add all those gaps together, and you get the loss."
        ) as t:
            self.play(Create(errors, lag_ratio=0.1), run_time=t.duration * 0.6)
            self.play(Write(cap), run_time=t.duration * 0.4)

        big = brand_text("loss = HIGH", size=32, color=PINK, weight=BOLD)
        big.move_to([0, -4.5, 0])
        self.play(FadeIn(big), run_time=0.5)

        # Improve the fit.
        good_m, good_c = 0.72, 1.4
        good = ax.plot(lambda x: good_m * x + good_c, x_range=[0.5, 9.5],
                       color=ACCENT, stroke_width=7)
        errors2 = VGroup(*[
            DashedLine(ax.c2p(x, y), ax.c2p(x, good_m * x + good_c),
                       color=GOLD, stroke_width=5, dash_length=0.12)
            for x, y in zip(XS, YS)
        ])
        small = brand_text("loss = LOW", size=32, color=ACCENT, weight=BOLD)
        small.move_to([0, -4.5, 0])

        with self.voiceover(
            text="Training is just the search for the line that makes this number "
                 "as small as possible."
        ) as t:
            self.play(
                Transform(bad, good), Transform(errors, errors2),
                Transform(big, small), run_time=t.duration * 0.75,
            )
            self.wait(t.duration * 0.25)

        self.play(FadeOut(cap), run_time=0.3)
        punch = brand_text("Lower loss = better model.", size=30,
                           weight=BOLD, color=ACCENT)
        punch.move_to([0, -5.2, 0])
        with self.voiceover(text="Lower loss means a better model. That is the whole game.") as t:
            self.play(Write(punch), run_time=t.duration * 0.65)
            self.wait(t.duration * 0.35)
        self.wait(0.5)
