"""ML Basics #1 — What is Machine Learning? (rules written vs rules learned)."""
from __future__ import annotations

from manim import (
    BOLD,
    Arrow,
    Create,
    FadeIn,
    FadeOut,
    RoundedRectangle,
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


def _box(label: str, color: str, width: float = 3.4, height: float = 1.15) -> VGroup:
    rect = RoundedRectangle(
        width=width, height=height, corner_radius=0.22,
        stroke_color=color, stroke_width=5, fill_color=color, fill_opacity=0.12,
    )
    text = brand_text(label, size=26, color=FG)
    if text.width > width * 0.86:
        text.scale_to_fit_width(width * 0.86)
    text.move_to(rect.get_center())
    return VGroup(rect, text)


class WhatIsML(VoiceBrandScene):
    SERIES = "ML BASICS #1"
    TITLE = "What Is Machine Learning?"
    SOURCE = "Concept explainer"

    def body(self) -> None:
        # ---------- traditional programming ----------
        heading = brand_text("Traditional programming", size=27, color=MUTED)
        heading.move_to([0, 4.6, 0])

        data_in = _box("Data", BLUE).move_to([0, 3.1, 0])
        rules_in = _box("Rules you write", GOLD).move_to([0, 1.5, 0])
        arrow1 = Arrow([0, 1.0, 0], [0, 0.1, 0], color=MUTED, buff=0.05, stroke_width=5)
        answers = _box("Answers", ACCENT).move_to([0, -0.6, 0])

        with self.voiceover(
            text="Normally, you write the rules. You give a computer data and "
                 "instructions, and it gives you answers."
        ) as t:
            self.play(FadeIn(heading), run_time=t.duration * 0.2)
            self.play(FadeIn(data_in), FadeIn(rules_in), run_time=t.duration * 0.4)
            self.play(Create(arrow1), FadeIn(answers), run_time=t.duration * 0.4)

        old = VGroup(heading, data_in, rules_in, arrow1, answers)

        with self.voiceover(
            text="Machine learning flips that around."
        ) as t:
            self.play(FadeOut(old), run_time=t.duration)

        # ---------- machine learning ----------
        heading2 = brand_text("Machine learning", size=27, color=ACCENT)
        heading2.move_to([0, 4.6, 0])

        data2 = _box("Data", BLUE).move_to([0, 3.1, 0])
        answers2 = _box("Answers", ACCENT).move_to([0, 1.5, 0])
        arrow2 = Arrow([0, 1.0, 0], [0, 0.1, 0], color=MUTED, buff=0.05, stroke_width=5)
        rules_out = _box("Rules it learns", PINK).move_to([0, -0.6, 0])

        with self.voiceover(
            text="You give it the data and the answers. It figures out the rules by itself."
        ) as t:
            self.play(FadeIn(heading2), run_time=t.duration * 0.18)
            self.play(FadeIn(data2), FadeIn(answers2), run_time=t.duration * 0.42)
            self.play(Create(arrow2), FadeIn(rules_out), run_time=t.duration * 0.40)

        cap = self.caption("Nobody wrote those rules by hand.", y=-2.6, size=29)
        with self.voiceover(
            text="Nobody wrote those rules by hand. That is the whole idea."
        ) as t:
            self.play(Write(cap), run_time=t.duration * 0.5)
            self.wait(t.duration * 0.5)

        punch = brand_text("Learn the rules from examples.", size=30,
                           weight=BOLD, color=ACCENT)
        punch.move_to([0, -4.4, 0])
        with self.voiceover(
            text="Machine learning learns the rules from examples."
        ) as t:
            self.play(Write(punch), run_time=t.duration * 0.7)
            self.wait(t.duration * 0.3)
        self.wait(0.6)
