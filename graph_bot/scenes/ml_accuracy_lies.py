"""ML Basics #10 — Why accuracy lies: precision, recall and imbalanced data."""
from __future__ import annotations

from manim import BOLD, FadeIn, FadeOut, VGroup, Write

from graph_bot.scenes._base import (
    ACCENT,
    BLUE,
    GOLD,
    MUTED,
    PINK,
    VoiceBrandScene,
    brand_text,
)
from graph_bot.scenes.components import chip, labeled_box


class AccuracyLies(VoiceBrandScene):
    SERIES = "ML BASICS #10"
    TITLE = "Why Accuracy Lies"
    SUBTITLE = "Precision & recall"
    SOURCE = "Concept explainer"

    def body(self) -> None:
        # 100 chips: 99 healthy, 1 sick.
        grid = VGroup(*[chip(BLUE, size=0.42, fill=0.4) for _ in range(100)])
        grid.arrange_in_grid(rows=10, cols=10, buff=0.16)
        grid.move_to([0, 2.3, 0])
        grid[54].set_stroke(PINK).set_fill(PINK, opacity=0.95)

        with self.voiceover(
            text="Imagine a disease that affects one person in a hundred. "
                 "Here are a hundred patients — one is sick."
        ) as t:
            self.play(FadeIn(grid, lag_ratio=0.012), run_time=t.duration * 0.75)
            self.wait(t.duration * 0.25)

        cheat = labeled_box('Model: "nobody is sick"', GOLD, width=6.6, height=1.05, text_size=25)
        cheat.move_to([0, -1.5, 0])
        score = brand_text("99% accurate ✅", size=34, color=GOLD, weight=BOLD)
        score.move_to([0, -2.8, 0])

        with self.voiceover(
            text="Now here is a lazy model. It always says nobody is sick. Never checks anything."
        ) as t:
            self.play(FadeIn(cheat), run_time=t.duration * 0.6)
            self.wait(t.duration * 0.4)

        with self.voiceover(
            text="Its accuracy? Ninety nine percent. It sounds fantastic."
        ) as t:
            self.play(Write(score), run_time=t.duration * 0.6)
            self.wait(t.duration * 0.4)

        fail = brand_text("…and it missed the only sick patient ❌",
                          size=27, color=PINK, weight=BOLD)
        fail.move_to([0, -3.9, 0])
        if fail.width > 8.3:
            fail.scale_to_fit_width(8.3)

        with self.voiceover(
            text="But it missed the one person who actually needed help. "
                 "The single case that mattered."
        ) as t:
            self.play(grid[54].animate.scale(1.8), run_time=t.duration * 0.35)
            self.play(Write(fail), run_time=t.duration * 0.65)

        self.play(FadeOut(cheat), FadeOut(score), FadeOut(fail), run_time=0.5)

        prec = labeled_box("PRECISION — of flagged, how many were right?",
                           ACCENT, width=8.2, height=1.0, text_size=21)
        prec.move_to([0, -1.7, 0])
        rec = labeled_box("RECALL — of the sick, how many did we catch?",
                          PINK, width=8.2, height=1.0, text_size=21)
        rec.move_to([0, -3.1, 0])

        with self.voiceover(
            text="This is why we use precision and recall instead. Precision asks: "
                 "of everything we flagged, how much was right? Recall asks: "
                 "of everything we should have caught, how much did we find?"
        ) as t:
            self.play(FadeIn(prec), run_time=t.duration * 0.4)
            self.play(FadeIn(rec), run_time=t.duration * 0.6)

        punch = brand_text("Accuracy alone can hide total failure.", size=27,
                           weight=BOLD, color=ACCENT)
        punch.move_to([0, -5.3, 0])
        if punch.width > 8.3:
            punch.scale_to_fit_width(8.3)
        with self.voiceover(
            text="On imbalanced data, accuracy alone can hide a total failure."
        ) as t:
            self.play(Write(punch), run_time=t.duration * 0.7)
            self.wait(t.duration * 0.3)
        self.wait(0.6)
