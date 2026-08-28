"""ML Basics #8 — Training vs inference: the slow part and the fast part."""
from __future__ import annotations

from manim import BOLD, Create, FadeIn, FadeOut, Indicate, VGroup, Write

from graph_bot.scenes._base import (
    ACCENT,
    BLUE,
    GOLD,
    MUTED,
    PINK,
    VoiceBrandScene,
    brand_text,
)
from graph_bot.scenes.components import chip_grid, down_arrow, labeled_box


class TrainingVsInference(VoiceBrandScene):
    SERIES = "ML BASICS #8"
    TITLE = "Training vs Inference"
    SUBTITLE = "Learning it, then using it"
    SOURCE = "Concept explainer"

    def body(self) -> None:
        # ---------------- training ----------------
        head1 = brand_text("TRAINING", size=30, color=GOLD, weight=BOLD)
        head1.move_to([0, 4.7, 0])
        note1 = brand_text("slow • expensive • done once", size=23, color=MUTED)
        note1.move_to([0, 4.1, 0])

        data = chip_grid(15, BLUE, rows=3, cols=5)
        data.scale(0.8).move_to([0, 2.7, 0])
        arrow1 = down_arrow(1.9, 1.25)
        model_box = labeled_box("MODEL  (learning…)", GOLD, width=5.6, height=1.1, text_size=25)
        model_box.move_to([0, 0.6, 0])

        with self.voiceover(
            text="Training is when the model actually learns. You feed it mountains "
                 "of data, over and over."
        ) as t:
            self.play(FadeIn(head1), FadeIn(note1), run_time=t.duration * 0.25)
            self.play(FadeIn(data, lag_ratio=0.04), run_time=t.duration * 0.45)
            self.play(Create(arrow1), FadeIn(model_box), run_time=t.duration * 0.3)

        with self.voiceover(
            text="This can take hours, or for the biggest models, months and millions "
                 "of dollars."
        ) as t:
            self.play(Indicate(model_box, color=GOLD, scale_factor=1.06),
                      run_time=t.duration * 0.5)
            self.wait(t.duration * 0.5)

        top = VGroup(head1, note1, data, arrow1, model_box)
        self.play(top.animate.scale(0.72).shift([0, 1.5, 0]), run_time=0.6)

        # ---------------- inference ----------------
        head2 = brand_text("INFERENCE", size=30, color=ACCENT, weight=BOLD)
        head2.move_to([0, -0.6, 0])
        note2 = brand_text("fast • cheap • every single use", size=23, color=MUTED)
        note2.move_to([0, -1.2, 0])

        one = labeled_box("one new input", BLUE, width=4.6, height=0.95, text_size=24)
        one.move_to([0, -2.3, 0])
        arrow2 = down_arrow(-2.9, -3.6)
        answer = labeled_box("answer", ACCENT, width=4.6, height=0.95, text_size=24)
        answer.move_to([0, -4.3, 0])

        with self.voiceover(
            text="Inference is when you actually use it. One input goes in, "
                 "one answer comes out."
        ) as t:
            self.play(FadeIn(head2), FadeIn(note2), run_time=t.duration * 0.3)
            self.play(FadeIn(one), run_time=t.duration * 0.3)
            self.play(Create(arrow2), FadeIn(answer), run_time=t.duration * 0.4)

        with self.voiceover(
            text="That part takes milliseconds. It is what happens every time you "
                 "send a message to a chatbot."
        ) as t:
            self.play(Indicate(answer, color=ACCENT, scale_factor=1.08),
                      run_time=t.duration * 0.45)
            self.wait(t.duration * 0.55)

        punch = brand_text("Train once. Infer forever.", size=30,
                           weight=BOLD, color=ACCENT)
        punch.move_to([0, -5.2, 0])
        with self.voiceover(text="Train once. Then use it forever.") as t:
            self.play(Write(punch), run_time=t.duration * 0.7)
            self.wait(t.duration * 0.3)
        self.wait(0.5)
