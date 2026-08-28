"""Charts Lie #1 — the truncated y-axis: 2% drawn to look like 200%."""
from __future__ import annotations

from manim import (
    BOLD,
    Axes,
    Create,
    FadeIn,
    FadeOut,
    Rectangle,
    Transform,
    VGroup,
    Write,
)

from graph_bot.scenes._base import (
    ACCENT,
    BLUE,
    FG,
    GOLD,
    GRID,
    MUTED,
    PINK,
    VoiceBrandScene,
    brand_text,
)

LABELS = ["A", "B", "C", "D"]
VALUES = [96.0, 97.0, 97.5, 98.0]   # a nearly flat series


class TruncatedAxis(VoiceBrandScene):
    SERIES = "CHARTS LIE #1"
    TITLE = "Grew 200%… or 2%?"
    SUBTITLE = "The truncated axis"
    SOURCE = "Concept explainer"

    def _chart(self, y_low: float, y_high: float, colour: str) -> tuple[Axes, VGroup]:
        """Bar chart whose y-axis starts at y_low — the whole trick of this episode."""
        step = max(1.0, (y_high - y_low) / 4)
        ax = Axes(
            x_range=[0, 5, 1], y_range=[y_low, y_high, step],
            x_length=6.4, y_length=5.4, tips=False,
            axis_config={"color": GRID, "stroke_width": 3},
            x_axis_config={"include_ticks": False},
        )
        ax.move_to([0.3, 0.6, 0])

        # Axis numbers as plain Text — Manim's include_numbers renders via LaTeX,
        # which this project deliberately does not depend on.
        ticks = VGroup()
        value = y_low
        while value <= y_high + 1e-9:
            lbl = brand_text(f"{value:.0f}", size=21, color=MUTED)
            lbl.move_to(ax.c2p(0, value))
            lbl.shift([-0.45, 0, 0])
            ticks.add(lbl)
            value += step
        ax.add(ticks)

        bars = VGroup()
        for i, value in enumerate(VALUES):
            x = i + 0.9
            bottom = ax.c2p(x, y_low)
            top = ax.c2p(x, value)
            height = top[1] - bottom[1]
            width = abs(ax.c2p(1, y_low)[0] - ax.c2p(0, y_low)[0]) * 0.62

            rect = Rectangle(width=width, height=max(height, 0.02),
                             fill_color=colour, fill_opacity=0.95, stroke_width=0)
            rect.move_to([bottom[0], bottom[1] + height / 2, 0])

            label = brand_text(LABELS[i], size=22, color=MUTED)
            label.move_to([bottom[0], bottom[1] - 0.35, 0])
            bars.add(VGroup(rect, label))
        return ax, bars

    def body(self) -> None:
        # --- the misleading version: axis starts at 95 ---
        ax1, bars1 = self._chart(95, 99, PINK)
        cap = self.caption("Sales are EXPLODING! 🚀", y=-4.6, size=30, color=PINK)

        with self.voiceover(
            text="Look at this chart. Sales look like they have exploded — "
                 "the last bar is several times taller than the first."
        ) as t:
            self.play(Create(ax1), run_time=t.duration * 0.35)
            self.play(FadeIn(bars1, lag_ratio=0.18), run_time=t.duration * 0.4)
            self.play(Write(cap), run_time=t.duration * 0.25)

        warn = brand_text("…but look at the axis", size=26, color=GOLD)
        warn.move_to([0, -5.5, 0])
        with self.voiceover(
            text="But check the numbers on the side. This axis does not start at zero. "
                 "It starts at ninety five."
        ) as t:
            self.play(FadeIn(warn), run_time=t.duration * 0.3)
            self.play(ax1.get_y_axis().animate.set_color(GOLD), run_time=t.duration * 0.7)

        # --- the honest version: axis starts at 0 ---
        ax2, bars2 = self._chart(0, 100, ACCENT)
        cap2 = self.caption("…a 2% change. 😐", y=-4.6, size=30, color=ACCENT)

        with self.voiceover(
            text="Start the axis at zero, and here is the same data. "
                 "The bars are almost identical."
        ) as t:
            self.play(FadeOut(warn), run_time=t.duration * 0.12)
            self.play(
                Transform(ax1, ax2), Transform(bars1, bars2), Transform(cap, cap2),
                run_time=t.duration * 0.88,
            )
        self.wait(0.5)

        punch = brand_text("Always check where the axis starts.", size=28,
                           weight=BOLD, color=ACCENT)
        punch.move_to([0, -5.3, 0])
        if punch.width > 8.3:
            punch.scale_to_fit_width(8.3)
        with self.voiceover(
            text="Same numbers. Completely different story. Always check where the "
                 "axis starts."
        ) as t:
            self.play(Write(punch), run_time=t.duration * 0.6)
            self.wait(t.duration * 0.4)
        self.wait(0.5)
