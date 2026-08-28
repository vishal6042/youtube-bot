"""K-means clustering — how a computer finds groups with no labels."""
from __future__ import annotations

import numpy as np
from manim import (
    BOLD,
    Create,
    FadeIn,
    FadeOut,
    Star,
    Transform,
    VGroup,
    Write,
)
from manim import Axes
from manim import Dot as MDot

from graph_bot.scenes._base import (
    ACCENT,
    BLUE,
    FG,
    GRID,
    MUTED,
    PINK,
    GOLD,
    BrandScene,
    brand_text,
)

CLUSTER_COLORS = [ACCENT, PINK, BLUE]


def _make_points(seed: int = 7):
    rng = np.random.default_rng(seed)
    centres = [(2.6, 7.2), (7.4, 7.0), (5.0, 2.8)]
    pts = []
    for cx, cy in centres:
        pts.append(rng.normal([cx, cy], 0.85, size=(14, 2)))
    return np.clip(np.vstack(pts), 0.5, 9.5)


def _kmeans_steps(points: np.ndarray, k: int = 3, iters: int = 4):
    """Run k-means from a deliberately poor start; record each step."""
    centroids = np.array([[1.5, 3.0], [3.0, 4.2], [8.0, 3.5]])
    history = []
    for _ in range(iters):
        d = np.linalg.norm(points[:, None, :] - centroids[None, :, :], axis=2)
        labels = d.argmin(axis=1)
        history.append((labels.copy(), centroids.copy()))
        for i in range(k):
            if (labels == i).any():
                centroids[i] = points[labels == i].mean(axis=0)
    history.append((labels.copy(), centroids.copy()))
    return history


class KMeans(BrandScene):
    TITLE = "How Computers Find Patterns"
    SUBTITLE = "K-means clustering"
    SOURCE = "Concept explainer"

    def body(self) -> None:
        ax = Axes(
            x_range=[0, 10, 1], y_range=[0, 10, 1],
            x_length=7.0, y_length=6.6, tips=False,
            axis_config={"color": GRID, "stroke_width": 3, "include_ticks": False},
        )
        ax.move_to([0, 0.5, 0])
        self.play(Create(ax), run_time=0.7)

        points = _make_points()
        dots = VGroup(*[MDot(ax.c2p(x, y), color=MUTED, radius=0.09) for x, y in points])
        self.play(FadeIn(dots, lag_ratio=0.03), run_time=1.3)

        cap = self.caption("Just dots. No labels.")
        self.play(Write(cap), run_time=0.8)
        self.wait(0.7)

        history = _kmeans_steps(points)
        labels0, cent0 = history[0]

        stars = VGroup(*[
            Star(n=5, outer_radius=0.22, color=CLUSTER_COLORS[i], fill_opacity=1)
            .move_to(ax.c2p(*cent0[i]))
            for i in range(3)
        ])
        cap2 = self.caption("Drop 3 guesses…", color=GOLD)
        self.play(Transform(cap, cap2), run_time=0.6)
        self.play(FadeIn(stars, scale=1.5), run_time=0.8)

        cap3 = self.caption("…colour each dot by its nearest guess", color=FG)
        self.play(Transform(cap, cap3), run_time=0.7)

        for step, (labels, centroids) in enumerate(history):
            # 1. recolour points to nearest centroid
            self.play(
                *[dots[i].animate.set_color(CLUSTER_COLORS[labels[i]])
                  for i in range(len(dots))],
                run_time=0.55,
            )
            # 2. move centroids to the middle of their cluster
            if step + 1 < len(history):
                nxt = history[step + 1][1]
                self.play(
                    *[stars[i].animate.move_to(ax.c2p(*nxt[i])) for i in range(3)],
                    run_time=0.55,
                )
            if step == 0:
                cap4 = self.caption("…then move each guess to its centre", color=FG)
                self.play(Transform(cap, cap4), run_time=0.5)

        cap5 = self.caption("Repeat → the groups appear ✅", color=ACCENT)
        self.play(Transform(cap, cap5), run_time=0.8)
        self.wait(1.4)

        self.play(FadeOut(cap), run_time=0.4)
        punch = brand_text("No human labelled a thing.", size=31, weight=BOLD, color=FG)
        punch.move_to([0, -5.9, 0])
        self.play(Write(punch), run_time=1.0)
        self.wait(1.7)
