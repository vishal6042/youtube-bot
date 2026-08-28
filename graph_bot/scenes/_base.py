"""Shared Manim setup: brand styling, vertical canvas, title/footer furniture.

Two base classes:
  * ``BrandScene``      — silent scene (music added later by the pipeline)
  * ``VoiceBrandScene`` — narrated scene (Edge neural TTS, animation auto-synced)

Both share the same furniture via ``_Furniture`` so every concept video looks
identical to the matplotlib data videos.

Canvas: 1080x1920 px mapped to a 9 x 16 Manim coordinate space (x: -4.5..4.5,
y: -8..8), so positioning is intuitive.
"""
from __future__ import annotations

import textwrap
from contextlib import contextmanager

from manim import (
    BOLD,
    DOWN,
    Line,
    Scene,
    Text,
    VGroup,
    config,
)
from manim_voiceover import VoiceoverScene

# --- brand palette (matches render.py) ---
BG = "#0a0e1c"
FG = "#f2f5fa"
MUTED = "#9aa4b2"
ACCENT = "#5ee0c8"
GRID = "#2a3350"
WARN = "#ff7b54"
GOLD = "#ffd60a"
PINK = "#f72585"
BLUE = "#4cc9f0"
PURPLE = "#7b6cf6"

SERIES_COLORS = [ACCENT, BLUE, PURPLE, PINK, GOLD, WARN]

# Fonts that exist on a stock Windows install; Pango picks the first available.
FONT = "Segoe UI"

# Default narration voice (see: python -m graph_bot.scenes.edge_speech --list)
DEFAULT_VOICE = "en-US-AriaNeural"

# Layout bands (Manim units; frame spans y -8..8).
# Scene content must stay ABOVE PUNCH_FLOOR so it never collides with captions.
PUNCH_FLOOR = -5.4
CAPTION_Y = -6.65      # burned-in narration subtitles live here
CAPTION_SIZE = 20
CAPTION_WRAP = 42      # characters per line
CAPTION_MAX_LINES = 3

# Vertical canvas
config.pixel_width = 1080
config.pixel_height = 1920
config.frame_rate = 30
config.frame_height = 16.0
config.frame_width = 9.0
config.background_color = BG


def brand_text(text: str, size: int = 34, color: str = FG, weight=None) -> Text:
    kwargs = {"font_size": size, "color": color, "font": FONT}
    if weight:
        kwargs["weight"] = weight
    return Text(text, **kwargs)


class _Furniture:
    """Title block, optional series badge, source credit and footer."""

    TITLE = ""
    SUBTITLE = ""
    SOURCE = ""
    SERIES = ""  # e.g. "ML BASICS #1"

    def add_furniture(self) -> None:
        top = 7.45
        if self.SERIES:
            badge = brand_text(self.SERIES, size=22, color=ACCENT, weight=BOLD)
            badge.move_to([0, top, 0])
            self.add(badge)

        title = brand_text(self.TITLE, size=46, weight=BOLD)
        # Long titles would run off a 9-unit-wide vertical frame — shrink to fit.
        max_w = config.frame_width * 0.92
        if title.width > max_w:
            title.scale_to_fit_width(max_w)
        title.move_to([0, 6.75, 0])

        rule = Line([-1.6, 0, 0], [1.6, 0, 0], color=ACCENT, stroke_width=5)
        rule.next_to(title, DOWN, buff=0.26)

        group = VGroup(title, rule)
        if self.SUBTITLE:
            sub = brand_text(self.SUBTITLE, size=26, color=MUTED)
            if sub.width > max_w:
                sub.scale_to_fit_width(max_w)
            sub.next_to(rule, DOWN, buff=0.26)
            group.add(sub)
        self.add(group)

        if self.SOURCE:
            credit = brand_text(f"Source: {self.SOURCE}", size=19, color=MUTED)
            credit.move_to([0, -7.52, 0])
            self.add(credit)

        footer = brand_text("Data in Motion", size=16, color=GRID)
        footer.move_to([0, -7.85, 0])
        self.add(footer)

    def caption(self, text: str, y: float = -5.9, size: int = 28, color: str = ACCENT) -> Text:
        """A short explanatory line placed under the visual."""
        t = brand_text(text, size=size, color=color)
        max_w = config.frame_width * 0.94
        if t.width > max_w:
            t.scale_to_fit_width(max_w)
        t.move_to([0, y, 0])
        return t

    def body(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class BrandScene(_Furniture, Scene):
    """Silent branded scene; the pipeline adds mood music afterwards."""

    def construct(self) -> None:
        self.add_furniture()
        self.body()


class VoiceBrandScene(_Furniture, VoiceoverScene):
    """Branded scene narrated with free Edge neural TTS.

    Use ``with self.voiceover(text=...) as t:`` and drive animations with
    ``run_time=t.duration`` so visuals stay in sync with the narration.

    The narration is also burned in as an on-screen subtitle (most Shorts are
    watched muted), rendered in the reserved band below ``PUNCH_FLOOR``.
    """

    VOICE = DEFAULT_VOICE
    CAPTIONS = True

    def construct(self) -> None:
        from graph_bot.scenes.edge_speech import EdgeService

        self.set_speech_service(EdgeService(voice=self.VOICE))
        self.add_furniture()
        self.body()

    # -- burned-in subtitles ---------------------------------------------- #
    def _subtitle(self, text: str) -> Text:
        """Wrapped, size-clamped subtitle for one narration segment."""
        wrapped = textwrap.wrap(" ".join(text.split()), width=CAPTION_WRAP)
        # Too many lines would run into the source credit — tighten the wrap.
        if len(wrapped) > CAPTION_MAX_LINES:
            wrapped = textwrap.wrap(" ".join(text.split()), width=CAPTION_WRAP + 14)
        wrapped = wrapped[:CAPTION_MAX_LINES]

        t = Text(
            "\n".join(wrapped), font=FONT, font_size=CAPTION_SIZE,
            color=FG, line_spacing=0.65,
        )
        max_w = config.frame_width * 0.94
        if t.width > max_w:
            t.scale_to_fit_width(max_w)
        t.move_to([0, CAPTION_Y, 0])
        return t

    @contextmanager
    def voiceover(self, text: str | None = None, **kwargs):  # type: ignore[override]
        """Speak ``text`` and show it on screen for the same span."""
        with super().voiceover(text=text, **kwargs) as tracker:
            subtitle = self._subtitle(text) if (self.CAPTIONS and text) else None
            if subtitle is not None:
                self.add(subtitle)
            try:
                yield tracker
            finally:
                if subtitle is not None:
                    self.remove(subtitle)
