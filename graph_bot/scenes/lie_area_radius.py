"""Charts Lie #14 — area vs radius: doubling the radius quadruples the circle.

Infographics routinely scale a bubble's RADIUS by the value. Because area grows
with the square of the radius, a value that doubled is drawn four times bigger.
"""
from __future__ import annotations

from manim import (
    BOLD,
    Circle,
    FadeIn,
    FadeOut,
    GrowFromCenter,
    Transform,
    VGroup,
    Write,
)

from graph_bot.scenes._base import (
    ACCENT,
    GOLD,
    MUTED,
    PINK,
    VoiceBrandScene,
    brand_text,
)

SMALL_R = 0.95          # circle for the "10" value
LEFT_X, RIGHT_X = -2.0, 2.0
ROW_Y = 1.2


class AreaVsRadius(VoiceBrandScene):
    SERIES = "CHARTS LIE #14"
    TITLE = "This Circle Is 4× Too Big"
    SUBTITLE = "Area vs radius"
    SOURCE = "Concept explainer"

    def _bubble(self, radius: float, x: float, colour: str, label: str,
                caption: str) -> VGroup:
        c = Circle(radius=radius, color=colour, fill_color=colour,
                   fill_opacity=0.45, stroke_width=5)
        c.move_to([x, ROW_Y, 0])
        val = brand_text(label, size=32, color=colour, weight=BOLD)
        val.move_to([x, ROW_Y, 0])
        cap = brand_text(caption, size=21, color=MUTED)
        cap.move_to([x, ROW_Y - radius - 0.55, 0])
        return VGroup(c, val, cap)

    def body(self) -> None:
        left = self._bubble(SMALL_R, LEFT_X, ACCENT, "10", "last year")

        with self.voiceover(
            text="Last year's number, drawn as a circle. Ten."
        ) as t:
            self.play(GrowFromCenter(left), run_time=t.duration * 0.7)
            self.wait(t.duration * 0.3)

        # The wrong way: radius doubled -> the blob looks four times bigger.
        wrong = self._bubble(SMALL_R * 2, RIGHT_X, PINK, "20", "this year")
        with self.voiceover(
            text="This year, twenty. So they double the radius."
        ) as t:
            self.play(GrowFromCenter(wrong), run_time=t.duration)

        shout = brand_text("Looks 4× bigger 😳", size=30, color=PINK)
        shout.move_to([0, -3.3, 0])
        with self.voiceover(
            text="But that quadruples the area. Your eye reads four times, not two."
        ) as t:
            self.play(Write(shout), run_time=t.duration * 0.45)
            self.play(wrong[0].animate.set_stroke(GOLD, width=8),
                      run_time=t.duration * 0.55)

        # The honest way: scale by area, so radius grows by sqrt(2).
        right_ok = self._bubble(SMALL_R * (2 ** 0.5), RIGHT_X, ACCENT, "20",
                                "this year (by area)")
        fixed = brand_text("Scaled by area ✓", size=30, color=ACCENT)
        fixed.move_to([0, -3.3, 0])
        with self.voiceover(
            text="Scale by area, and the honest circle is only slightly wider."
        ) as t:
            self.play(Transform(wrong, right_ok), Transform(shout, fixed),
                      run_time=t.duration)
        self.wait(0.4)

        punch = brand_text("Bubbles should scale by area.", size=28,
                           weight=BOLD, color=ACCENT)
        punch.move_to([0, -5.3, 0])
        if punch.width > 8.3:
            punch.scale_to_fit_width(8.3)
        with self.voiceover(
            text="With bubbles, always ask: scaled by area, or by radius?"
        ) as t:
            self.play(FadeOut(shout), run_time=t.duration * 0.15)
            self.play(Write(punch), run_time=t.duration * 0.5)
            self.wait(t.duration * 0.35)
        self.wait(0.5)
