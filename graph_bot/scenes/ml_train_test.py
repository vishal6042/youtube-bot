"""ML Basics #3 — Train/test split: why you hide data from your own model."""
from __future__ import annotations

from manim import (
    BOLD,
    Create,
    FadeIn,
    FadeOut,
    RoundedRectangle,
    Transform,
    VGroup,
    Write,
)

from graph_bot.scenes._base import (
    ACCENT,
    BLUE,
    FG,
    GOLD,
    MUTED,
    PINK,
    VoiceBrandScene,
    brand_text,
)


def _chip(color: str, w: float = 0.62, h: float = 0.62) -> RoundedRectangle:
    return RoundedRectangle(
        width=w, height=h, corner_radius=0.12,
        stroke_color=color, stroke_width=3, fill_color=color, fill_opacity=0.55,
    )


class TrainTestSplit(VoiceBrandScene):
    SERIES = "ML BASICS #3"
    TITLE = "Train / Test Split"
    SUBTITLE = "Why you hide data from your model"
    SOURCE = "Concept explainer"

    def body(self) -> None:
        # A grid of 20 data chips.
        chips = VGroup(*[_chip(BLUE) for _ in range(20)])
        chips.arrange_in_grid(rows=4, cols=5, buff=0.34)
        chips.move_to([0, 2.6, 0])

        label = brand_text("Your dataset", size=26, color=MUTED)
        label.next_to(chips, direction=[0, 1, 0], buff=0.5)

        with self.voiceover(
            text="Say you have a dataset. It is tempting to train your model on all of it."
        ) as t:
            self.play(FadeIn(label), run_time=t.duration * 0.25)
            self.play(FadeIn(chips, lag_ratio=0.05), run_time=t.duration * 0.75)

        with self.voiceover(
            text="Do not. If you test on the same data you trained on, the model can "
                 "simply memorise the answers."
        ) as t:
            self.play(
                *[c.animate.set_stroke(PINK).set_fill(PINK, opacity=0.5) for c in chips],
                run_time=t.duration * 0.45,
            )
            warn = self.caption("Testing on training data = cheating", y=0.4, size=28, color=PINK)
            self.play(Write(warn), run_time=t.duration * 0.55)

        # Split 80 / 20.
        train, test = chips[:16], chips[4:][-4:]
        with self.voiceover(
            text="Instead, split it. Keep about eighty percent to train on…"
        ) as t:
            self.play(FadeOut(warn), run_time=t.duration * 0.2)
            self.play(
                *[c.animate.set_stroke(ACCENT).set_fill(ACCENT, opacity=0.55) for c in train],
                run_time=t.duration * 0.8,
            )

        with self.voiceover(
            text="…and lock the last twenty percent away. Your model never sees it."
        ) as t:
            self.play(
                *[c.animate.set_stroke(GOLD).set_fill(GOLD, opacity=0.7) for c in test],
                run_time=t.duration * 0.5,
            )
            self.play(test.animate.shift([0, -1.15, 0]), run_time=t.duration * 0.5)

        train_lbl = brand_text("TRAIN  •  80%", size=25, color=ACCENT, weight=BOLD)
        train_lbl.move_to([0, 0.55, 0])
        test_lbl = brand_text("TEST  •  20%  (hidden)", size=25, color=GOLD, weight=BOLD)
        test_lbl.move_to([0, -1.9, 0])

        with self.voiceover(
            text="Train on the green. Then, only at the very end, check the model "
                 "against the gold."
        ) as t:
            self.play(FadeIn(train_lbl), run_time=t.duration * 0.4)
            self.play(FadeIn(test_lbl), run_time=t.duration * 0.6)

        cap = self.caption("That score is the honest one.", y=-4.6, size=29)
        with self.voiceover(
            text="That score is the honest one, because it measures data the model "
                 "has genuinely never seen."
        ) as t:
            self.play(Write(cap), run_time=t.duration * 0.5)
            self.wait(t.duration * 0.5)

        self.play(FadeOut(cap), run_time=0.35)
        punch = brand_text("Never test on what you trained on.", size=29,
                           weight=BOLD, color=ACCENT)
        punch.move_to([0, -5.3, 0])
        with self.voiceover(text="Never test on what you trained on.") as t:
            self.play(Write(punch), run_time=t.duration * 0.75)
            self.wait(t.duration * 0.25)
        self.wait(0.6)
