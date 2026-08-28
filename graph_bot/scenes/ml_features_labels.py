"""ML Basics #4 — Features and labels: the inputs and the answer."""
from __future__ import annotations

from manim import BOLD, FadeIn, FadeOut, Indicate, VGroup, Write

from graph_bot.scenes._base import (
    ACCENT,
    BLUE,
    GOLD,
    MUTED,
    PINK,
    VoiceBrandScene,
    brand_text,
)
from graph_bot.scenes.components import labeled_box

ROWS = [
    ("1,200 sq ft", "3", "1995", "$240k"),
    ("1,800 sq ft", "4", "2008", "$390k"),
    ("2,400 sq ft", "5", "2015", "$520k"),
]


class FeaturesLabels(VoiceBrandScene):
    SERIES = "ML BASICS #4"
    TITLE = "Features & Labels"
    SUBTITLE = "Inputs vs the answer"
    SOURCE = "Concept explainer"

    def body(self) -> None:
        headers = VGroup(
            brand_text("Size", size=24, color=BLUE, weight=BOLD),
            brand_text("Beds", size=24, color=BLUE, weight=BOLD),
            brand_text("Year", size=24, color=BLUE, weight=BOLD),
            brand_text("Price", size=24, color=GOLD, weight=BOLD),
        )
        for i, h in enumerate(headers):
            h.move_to([-3.1 + i * 2.05, 3.6, 0])

        with self.voiceover(
            text="Imagine a table of houses. Each row is one example."
        ) as t:
            self.play(FadeIn(headers), run_time=t.duration * 0.5)
            self.wait(t.duration * 0.5)

        row_groups = VGroup()
        for r, row in enumerate(ROWS):
            g = VGroup()
            for i, cell in enumerate(row):
                colour = GOLD if i == 3 else MUTED
                c = brand_text(cell, size=22, color=colour)
                c.move_to([-3.1 + i * 2.05, 2.6 - r * 0.95, 0])
                g.add(c)
            row_groups.add(g)

        with self.voiceover(
            text="Size, bedrooms, year built. These columns are the features — "
                 "the information we feed in."
        ) as t:
            self.play(FadeIn(row_groups, lag_ratio=0.15), run_time=t.duration * 0.55)
            self.play(Indicate(VGroup(*headers[:3]), color=BLUE, scale_factor=1.15),
                      run_time=t.duration * 0.45)

        feat_box = labeled_box("FEATURES  (inputs)", BLUE, width=6.4, height=1.0, text_size=25)
        feat_box.move_to([0, -0.8, 0])
        self.play(FadeIn(feat_box), run_time=0.5)

        with self.voiceover(
            text="The last column, price, is the label. That is the answer we want "
                 "the model to predict."
        ) as t:
            self.play(Indicate(headers[3], color=GOLD, scale_factor=1.2),
                      run_time=t.duration * 0.45)
            lab_box = labeled_box("LABEL  (the answer)", GOLD, width=6.4, height=1.0, text_size=25)
            lab_box.move_to([0, -2.2, 0])
            self.play(FadeIn(lab_box), run_time=t.duration * 0.55)

        cap = self.caption("Features in → label out", y=-3.8, size=29)
        with self.voiceover(
            text="Features go in. The label comes out. Every supervised model works this way."
        ) as t:
            self.play(Write(cap), run_time=t.duration * 0.45)
            self.wait(t.duration * 0.55)

        self.play(FadeOut(cap), run_time=0.35)
        punch = brand_text("Good features beat clever models.", size=29,
                           weight=BOLD, color=ACCENT)
        punch.move_to([0, -5.2, 0])
        with self.voiceover(
            text="And in practice, good features usually beat a clever model."
        ) as t:
            self.play(Write(punch), run_time=t.duration * 0.7)
            self.wait(t.duration * 0.3)
        self.wait(0.5)
