"""Reusable visual building blocks for concept scenes.

Keeps the ML Basics series visually consistent and quick to author.
"""
from __future__ import annotations

from manim import (
    BOLD,
    Arrow,
    RoundedRectangle,
    VGroup,
)

from graph_bot.scenes._base import ACCENT, FG, MUTED, brand_text


def labeled_box(
    label: str,
    color: str,
    width: float = 3.4,
    height: float = 1.15,
    text_size: int = 26,
    fill: float = 0.12,
) -> VGroup:
    """A rounded, tinted box with centred text that always fits."""
    rect = RoundedRectangle(
        width=width, height=height, corner_radius=0.2,
        stroke_color=color, stroke_width=5,
        fill_color=color, fill_opacity=fill,
    )
    text = brand_text(label, size=text_size, color=FG)
    if text.width > width * 0.86:
        text.scale_to_fit_width(width * 0.86)
    text.move_to(rect.get_center())
    return VGroup(rect, text)


def chip(color: str, size: float = 0.62, fill: float = 0.55) -> RoundedRectangle:
    return RoundedRectangle(
        width=size, height=size, corner_radius=0.12,
        stroke_color=color, stroke_width=3,
        fill_color=color, fill_opacity=fill,
    )


def chip_grid(count: int, color: str, rows: int = 4, cols: int = 5,
              buff: float = 0.34) -> VGroup:
    grid = VGroup(*[chip(color) for _ in range(count)])
    grid.arrange_in_grid(rows=rows, cols=cols, buff=buff)
    return grid


def down_arrow(start_y: float, end_y: float, x: float = 0.0, color: str = MUTED) -> Arrow:
    return Arrow([x, start_y, 0], [x, end_y, 0], color=color, buff=0.05, stroke_width=5)


def column_header(text: str, color: str, x: float, y: float, size: int = 26):
    t = brand_text(text, size=size, color=color, weight=BOLD)
    t.move_to([x, y, 0])
    return t


def side_by_side(left: VGroup, right: VGroup, gap: float = 0.35, y: float = 0.0) -> VGroup:
    """Place two groups left/right within the 9-unit-wide vertical frame."""
    left.move_to([-2.1, y, 0])
    right.move_to([2.1, y, 0])
    return VGroup(left, right)


def bullet(text: str, color: str = ACCENT, size: int = 25):
    return brand_text(f"•  {text}", size=size, color=color)
