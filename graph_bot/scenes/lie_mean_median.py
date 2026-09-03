"""Charts Lie #9 — mean vs median: one outlier drags the "average" above everyone.

Ten people in a bar. Nine ordinary salaries and one billionaire. The average
income in the room becomes a number nobody in it actually earns.
"""
from __future__ import annotations

from manim import (
    BOLD,
    DOWN,
    DashedLine,
    FadeIn,
    FadeOut,
    GrowFromEdge,
    Rectangle,
    VGroup,
    Write,
)

from graph_bot.scenes._base import (
    ACCENT,
    GOLD,
    GRID,
    MUTED,
    PINK,
    VoiceBrandScene,
    brand_text,
)

# Nine ordinary salaries, in thousands.
SALARIES = [28, 31, 34, 36, 38, 41, 44, 47, 52]
BILLIONAIRE = 900          # thousands, drawn clipped — the point is it's off-scale

X0, X1 = -3.6, 3.6
BASE_Y = -2.6
MAX_H = 4.6
SCALE_MAX = 60.0           # bar height scale for the ordinary salaries


class MeanVsMedian(VoiceBrandScene):
    SERIES = "CHARTS LIE #9"
    TITLE = "A Billionaire Walks Into a Bar"
    SUBTITLE = "Mean vs median"
    SOURCE = "Concept explainer"

    def _bars(self, values: list[float]) -> VGroup:
        n = len(values)
        slot = (X1 - X0) / n
        width = slot * 0.62
        bars = VGroup()
        for i, v in enumerate(values):
            h = min(v / SCALE_MAX, 1.0) * MAX_H
            rect = Rectangle(width=width, height=max(h, 0.05),
                             fill_color=ACCENT, fill_opacity=0.92, stroke_width=0)
            rect.move_to([X0 + slot * (i + 0.5), BASE_Y + h / 2, 0])
            bars.add(rect)
        return bars

    def _marker(self, value: float, label: str, colour: str, above: bool) -> VGroup:
        y = BASE_Y + min(value / SCALE_MAX, 1.0) * MAX_H
        line = DashedLine([X0 - 0.4, y, 0], [X1 + 0.4, y, 0],
                          color=colour, stroke_width=5, dash_length=0.13)
        tag = brand_text(label, size=24, color=colour, weight=BOLD)
        tag.move_to([0, y + (0.42 if above else -0.42), 0])
        return VGroup(line, tag)

    def body(self) -> None:
        bars = self._bars(SALARIES)
        floor = brand_text("9 people in a bar", size=24, color=MUTED)
        floor.move_to([0, BASE_Y - 0.55, 0])

        with self.voiceover(
            text="Nine people in a bar. Salaries between thirty and fifty thousand."
        ) as t:
            self.play(GrowFromEdge(bars, DOWN,
                                   lag_ratio=0.12), run_time=t.duration * 0.7)
            self.play(FadeIn(floor), run_time=t.duration * 0.3)

        median = SALARIES[len(SALARIES) // 2]
        mean_before = sum(SALARIES) / len(SALARIES)
        m1 = self._marker(mean_before, f"average  ${mean_before:,.0f}k", GOLD, True)

        with self.voiceover(
            text="The average is thirty eight thousand. That fits the room."
        ) as t:
            self.play(FadeIn(m1), run_time=t.duration * 0.5)
            self.wait(t.duration * 0.5)

        # The billionaire arrives: a bar that runs off the top of the frame.
        slot = (X1 - X0) / (len(SALARIES) + 1)
        rich = Rectangle(width=slot * 0.62, height=MAX_H + 3.0,
                         fill_color=PINK, fill_opacity=0.95, stroke_width=0)
        rich.move_to([X1 + 0.1, BASE_Y + (MAX_H + 3.0) / 2, 0])
        rich_lbl = brand_text("+1 billionaire", size=22, color=PINK)
        rich_lbl.move_to([X1 + 0.1, BASE_Y - 0.55, 0])

        with self.voiceover(
            text="Then a billionaire walks in. Straight off the chart."
        ) as t:
            self.play(FadeIn(rich, shift=DOWN * 0.6), run_time=t.duration * 0.55)
            self.play(FadeIn(rich_lbl), run_time=t.duration * 0.45)

        everyone = SALARIES + [BILLIONAIRE]
        mean_after = sum(everyone) / len(everyone)
        m2 = self._marker(min(mean_after, SCALE_MAX * 0.99),
                          f"average  ${mean_after:,.0f}k", GOLD, True)
        med = self._marker(median, f"median  ${median}k", ACCENT, False)

        with self.voiceover(
            text="Now the average beats everyone who was already here."
        ) as t:
            self.play(FadeOut(m1), run_time=t.duration * 0.15)
            self.play(FadeIn(m2), run_time=t.duration * 0.85)

        with self.voiceover(
            text="The median barely moves. It still describes the room."
        ) as t:
            self.play(FadeIn(med), run_time=t.duration * 0.6)
            self.wait(t.duration * 0.4)

        punch = brand_text("One outlier breaks the average.", size=28,
                           weight=BOLD, color=ACCENT)
        punch.move_to([0, -5.3, 0])
        if punch.width > 8.3:
            punch.scale_to_fit_width(8.3)
        with self.voiceover(
            text="When you see average, ask for the median."
        ) as t:
            self.play(Write(punch), run_time=t.duration * 0.6)
            self.wait(t.duration * 0.4)
        self.wait(0.5)
