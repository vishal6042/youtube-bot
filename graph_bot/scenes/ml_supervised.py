"""ML Basics #5 — Supervised vs unsupervised learning."""
from __future__ import annotations

import numpy as np
from manim import BOLD, FadeIn, FadeOut, VGroup, Write
from manim import Dot as MDot

from graph_bot.scenes._base import (
    ACCENT,
    BLUE,
    GOLD,
    MUTED,
    PINK,
    VoiceBrandScene,
    brand_text,
)
from graph_bot.scenes.components import column_header

RNG = np.random.default_rng(5)


def _cloud(cx: float, cy: float, n: int, spread: float = 0.55):
    return RNG.normal([cx, cy], spread, size=(n, 2))


class SupervisedVsUnsupervised(VoiceBrandScene):
    SERIES = "ML BASICS #5"
    TITLE = "Supervised vs Unsupervised"
    SOURCE = "Concept explainer"

    def body(self) -> None:
        # ---------- supervised ----------
        head1 = column_header("SUPERVISED", ACCENT, 0, 4.5, size=30)
        sub1 = brand_text("you give it the answers", size=24, color=MUTED)
        sub1.move_to([0, 3.85, 0])

        a = _cloud(-1.3, 1.9, 9)
        b = _cloud(1.3, 1.9, 9)
        labelled = VGroup(
            *[MDot([x, y, 0], color=BLUE, radius=0.11) for x, y in a],
            *[MDot([x, y, 0], color=PINK, radius=0.11) for x, y in b],
        )
        tag1 = brand_text("cat", size=21, color=BLUE)
        tag1.move_to([-1.3, 0.75, 0])
        tag2 = brand_text("dog", size=21, color=PINK)
        tag2.move_to([1.3, 0.75, 0])

        with self.voiceover(
            text="There are two big families. In supervised learning, every example "
                 "comes with a label — this is a cat, this is a dog."
        ) as t:
            self.play(FadeIn(head1), FadeIn(sub1), run_time=t.duration * 0.3)
            self.play(FadeIn(labelled, lag_ratio=0.05), run_time=t.duration * 0.4)
            self.play(FadeIn(tag1), FadeIn(tag2), run_time=t.duration * 0.3)

        with self.voiceover(
            text="The model learns to copy those labels on data it has not seen."
        ) as t:
            self.wait(t.duration)

        group1 = VGroup(head1, sub1, labelled, tag1, tag2)
        self.play(group1.animate.shift([0, 0.3, 0]).scale(0.75), run_time=0.6)

        # ---------- unsupervised ----------
        head2 = column_header("UNSUPERVISED", GOLD, 0, -0.9, size=30)
        sub2 = brand_text("no answers at all", size=24, color=MUTED)
        sub2.move_to([0, -1.55, 0])

        c = _cloud(-1.2, -3.4, 9)
        d = _cloud(1.4, -3.4, 9)
        unlabelled = VGroup(*[MDot([x, y, 0], color=MUTED, radius=0.11)
                              for x, y in np.vstack([c, d])])

        with self.voiceover(
            text="In unsupervised learning, there are no labels. Just raw data."
        ) as t:
            self.play(FadeIn(head2), FadeIn(sub2), run_time=t.duration * 0.35)
            self.play(FadeIn(unlabelled, lag_ratio=0.05), run_time=t.duration * 0.65)

        with self.voiceover(
            text="The model has to find the structure on its own — grouping things "
                 "that look alike."
        ) as t:
            n = len(c)
            self.play(
                *[unlabelled[i].animate.set_color(ACCENT) for i in range(n)],
                *[unlabelled[i].animate.set_color(GOLD) for i in range(n, len(unlabelled))],
                run_time=t.duration * 0.6,
            )
            self.wait(t.duration * 0.4)

        punch = brand_text("Labels? Supervised. No labels? Unsupervised.",
                           size=25, weight=BOLD, color=ACCENT)
        punch.move_to([0, -5.2, 0])
        if punch.width > 8.3:
            punch.scale_to_fit_width(8.3)
        with self.voiceover(
            text="If you have labels, it is supervised. If you do not, it is unsupervised."
        ) as t:
            self.play(Write(punch), run_time=t.duration * 0.7)
            self.wait(t.duration * 0.3)
        self.wait(0.5)
