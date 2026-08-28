"""Charts Lie #2 — the inverted y-axis: a rise drawn as a fall.

Modelled on the infamous Florida "Stand Your Ground" gun-deaths graphic, where
the y-axis ran downwards so a sharp increase in deaths read as a decline. The
numbers here are illustrative, not the original dataset.
"""
from __future__ import annotations

from manim import (
    BOLD,
    Create,
    FadeIn,
    FadeOut,
    Line,
    Polygon,
    Rotate,
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

# year, deaths — a series that clearly RISES
POINTS = [(2000, 34), (2003, 40), (2005, 52), (2008, 66), (2011, 72), (2014, 78)]

X0, X1 = -3.2, 3.2          # plot box in Manim units
Y0, Y1 = -1.8, 4.2
V_MIN, V_MAX = 25.0, 85.0


def _x(year: float) -> float:
    lo, hi = POINTS[0][0], POINTS[-1][0]
    return X0 + (year - lo) / (hi - lo) * (X1 - X0)


class InvertedAxis(VoiceBrandScene):
    SERIES = "CHARTS LIE #2"
    TITLE = "The Chart That Was Upside Down"
    SUBTITLE = "The inverted axis"
    SOURCE = "Concept explainer"

    def _y(self, value: float, flipped: bool) -> float:
        """Map a value to a y position; `flipped` runs the axis downwards."""
        frac = (value - V_MIN) / (V_MAX - V_MIN)
        if flipped:
            frac = 1.0 - frac
        return Y0 + frac * (Y1 - Y0)

    def _plot(self, flipped: bool, colour: str) -> VGroup:
        axes = VGroup(
            Line([X0, Y0, 0], [X1, Y0, 0], color=GRID, stroke_width=3),
            Line([X0, Y0, 0], [X0, Y1, 0], color=GRID, stroke_width=3),
        )

        ticks = VGroup()
        for value in (25, 45, 65, 85):
            lbl = brand_text(f"{value}", size=20, color=MUTED)
            lbl.move_to([X0 - 0.55, self._y(value, flipped), 0])
            ticks.add(lbl)

        pts = [[_x(yr), self._y(v, flipped), 0] for yr, v in POINTS]
        line = VGroup()
        for a, b in zip(pts, pts[1:]):
            line.add(Line(a, b, color=colour, stroke_width=9))

        # Shaded area under (or over) the line, the way news graphics draw it.
        area = Polygon(*pts, [pts[-1][0], Y0, 0], [pts[0][0], Y0, 0],
                       fill_color=colour, fill_opacity=0.22, stroke_width=0)

        years = VGroup()
        for yr, _ in (POINTS[0], POINTS[-1]):
            lbl = brand_text(str(yr), size=20, color=MUTED)
            lbl.move_to([_x(yr), Y0 - 0.4, 0])
            years.add(lbl)

        return VGroup(axes, ticks, area, line, years)

    def body(self) -> None:
        flipped = self._plot(flipped=True, colour=ACCENT)
        cap = self.caption("Gun deaths are falling. 📉", y=-4.6, size=30, color=ACCENT)

        with self.voiceover(
            text="This chart falls to the bottom right. Deaths are dropping. Good news."
        ) as t:
            self.play(Create(flipped), run_time=t.duration * 0.6)
            self.play(Write(cap), run_time=t.duration * 0.4)

        # Point at the axis: the numbers count DOWNWARDS.
        warn = brand_text("…read the axis numbers", size=26, color=GOLD)
        warn.move_to([0, -5.2, 0])
        with self.voiceover(
            text="But look at the numbers. Twenty five on top, eighty five at the bottom. "
                 "This axis is upside down."
        ) as t:
            self.play(FadeIn(warn), run_time=t.duration * 0.25)
            self.play(flipped[1].animate.set_color(GOLD), run_time=t.duration * 0.75)

        # Flip it the right way up — same data, opposite story.
        upright = self._plot(flipped=False, colour=PINK)
        cap2 = self.caption("Deaths more than doubled. 📈", y=-4.6, size=30, color=PINK)
        with self.voiceover(
            text="Flip it the right way up. The same numbers more than doubled."
        ) as t:
            self.play(FadeOut(warn), run_time=t.duration * 0.1)
            self.play(Rotate(flipped, angle=0.0), run_time=0.01)
            self.play(
                FadeOut(flipped, shift=[0, 0.4, 0]),
                run_time=t.duration * 0.3,
            )
            self.play(Create(upright), FadeIn(cap2), run_time=t.duration * 0.5)
            self.play(FadeOut(cap), run_time=t.duration * 0.1)

        punch = brand_text("Check which way the axis counts.", size=28,
                           weight=BOLD, color=ACCENT)
        punch.move_to([0, -5.3, 0])
        if punch.width > 8.3:
            punch.scale_to_fit_width(8.3)
        with self.voiceover(
            text="Same data, opposite story. Check which way the axis counts."
        ) as t:
            self.play(Write(punch), run_time=t.duration * 0.6)
            self.wait(t.duration * 0.4)
        self.wait(0.5)
