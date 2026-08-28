"""Gradient descent — how an AI model 'learns' by rolling downhill."""
from __future__ import annotations

from manim import (
    BOLD,
    Axes,
    Create,
    Dot,
    FadeIn,
    FadeOut,
    Flash,
    Transform,
    Write,
    smooth,
)

# Absolute import: Manim loads scene files by path, so relative imports fail.
from graph_bot.scenes._base import (
    ACCENT,
    FG,
    GOLD,
    GRID,
    MUTED,
    WARN,
    BrandScene,
    brand_text,
)


def loss(x: float) -> float:
    """A gentle bowl with a slight wobble, so descent looks non-trivial."""
    return 0.35 * x**2 + 0.6


class GradientDescent(BrandScene):
    TITLE = "How AI Learns"
    SUBTITLE = "Gradient descent, visualized"
    SOURCE = "Concept explainer"

    def body(self) -> None:
        ax = Axes(
            x_range=[-3.2, 3.2, 1],
            y_range=[0, 4.2, 1],
            x_length=7.2,
            y_length=6.4,
            tips=False,
            axis_config={"color": GRID, "stroke_width": 3, "include_ticks": False},
        )
        ax.move_to([0, 0.4, 0])

        curve = ax.plot(loss, x_range=[-3.1, 3.1], color=ACCENT, stroke_width=7)

        x_label = brand_text("model settings", size=22, color=MUTED)
        x_label.next_to(ax, direction=[0, -1, 0], buff=0.3)
        y_label = brand_text("error", size=22, color=MUTED)
        y_label.rotate(1.5708).next_to(ax, direction=[-1, 0, 0], buff=0.25)

        self.play(Create(ax), run_time=0.8)
        self.play(Create(curve), run_time=1.4)
        self.play(FadeIn(x_label), FadeIn(y_label), run_time=0.5)

        cap = self.caption("Start with random settings…")
        self.play(Write(cap), run_time=0.8)

        # The learner starts high on the curve.
        x = -2.9
        dot = Dot(ax.c2p(x, loss(x)), color=GOLD, radius=0.16)
        self.play(FadeIn(dot, scale=1.6), run_time=0.6)
        self.wait(0.4)

        cap2 = self.caption("…then step downhill, again and again")
        self.play(Transform(cap, cap2), run_time=0.7)

        # Gradient descent steps: x <- x - lr * f'(x),  f'(x) = 0.7x
        lr = 0.28
        for i in range(11):
            x = x - lr * (0.7 * x)
            run = 0.42 if i < 6 else 0.30
            self.play(dot.animate.move_to(ax.c2p(x, loss(x))), run_time=run, rate_func=smooth)

        self.play(Flash(dot, color=FG, line_length=0.35, num_lines=14), run_time=0.7)

        cap3 = self.caption("Lowest error = the model has learned ✅", color=WARN)
        self.play(Transform(cap, cap3), run_time=0.8)
        self.wait(1.4)

        self.play(FadeOut(cap), run_time=0.4)
        done = brand_text("That's it. That's training.", size=32, weight=BOLD, color=FG)
        done.move_to([0, -5.9, 0])
        self.play(Write(done), run_time=1.0)
        self.wait(1.6)
