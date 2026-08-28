"""Generate YouTube thumbnails for exported videos.

Thumbnails are 1080x1920 portrait JPEGs — the Shorts cover shape, so they fill
a phone screen rather than sitting in a letterboxed 16:9 box. Each is built
from the brand palette plus a real frame lifted from near the end of the
video, so the chart shown is the actual finished chart rather than a mock-up.

Layout, top to bottom: series badge, huge wrapped title sized to be readable
at feed scale, accent rule, subtitle, the chart panel, and the source credit.

Usage:
    python -m graph_bot.thumbnail                      # newest export date
    python -m graph_bot.thumbnail --date 2026-08-10    # one export date
    python -m graph_bot.thumbnail --date 2026-08-10 --series money
    python -m graph_bot.thumbnail --force              # rebuild existing ones
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .config import PROJECT_ROOT, load_settings, load_topics, resolve_path, topic_series
from .queue import playlist_of
from .render import ACCENT, BG_BOTTOM, BG_TOP, FG, MUTED, ffmpeg_exe

WIDTH, HEIGHT = 1080, 1920
# YouTube stores every thumbnail at 16:9 (120x90 up to 1280x720), so the portrait
# cover above is never actually used as the video's thumbnail. This is the one
# that is.
WIDE_WIDTH, WIDE_HEIGHT = 1280, 720

# Where the still is grabbed from, as a fraction of the video duration. Late
# enough that the chart has finished animating, early enough to miss any
# fade-out on the final frames.
FRAME_AT = 0.88

# The grabbed frame carries its own title block and source credit, which the
# cover redraws much larger. Trim both off so they are not shown twice.
CROP_TOP, CROP_BOTTOM = 0.135, 0.085

# Font candidates, best first; matplotlib's bundled DejaVu is the guaranteed
# fallback so this works on a machine with no Segoe/Arial.
_BOLD = ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]
_REGULAR = ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]


def _font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    import matplotlib

    roots = [Path("C:/Windows/Fonts"), Path(matplotlib.get_data_path()) / "fonts" / "ttf"]
    for name in candidates:
        for root in roots:
            path = root / name
            if path.exists():
                return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _gradient(width: int, height: int) -> Image.Image:
    """Vertical brand gradient, same two stops the videos use."""
    top = tuple(int(BG_TOP[i:i + 2], 16) for i in (1, 3, 5))
    bottom = tuple(int(BG_BOTTOM[i:i + 2], 16) for i in (1, 3, 5))
    base = Image.new("RGB", (1, height))
    px = base.load()
    for y in range(height):
        t = y / max(1, height - 1)
        px[0, y] = tuple(int(top[c] + (bottom[c] - top[c]) * t) for c in range(3))
    return base.resize((width, height), Image.BILINEAR)


def _grab_frame(video: Path, settings: dict[str, Any]) -> Image.Image | None:
    """Pull a single still from near the end of the video via ffmpeg."""
    duration = _duration(video, settings)
    if duration is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        still = Path(tmp) / "frame.png"
        cmd = [ffmpeg_exe(settings), "-y", "-loglevel", "error",
               "-ss", f"{duration * FRAME_AT:.2f}", "-i", str(video),
               "-frames:v", "1", str(still)]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except (subprocess.CalledProcessError, OSError):
            return None
        if not still.exists():
            return None
        return Image.open(still).convert("RGB").copy()


def _duration(video: Path, settings: dict[str, Any]) -> float | None:
    """Video duration in seconds, read from ffmpeg's own stderr report."""
    try:
        out = subprocess.run([ffmpeg_exe(settings), "-i", str(video)],
                             capture_output=True, text=True)
    except OSError:
        return None
    for line in (out.stderr or "").splitlines():
        if "Duration:" not in line:
            continue
        stamp = line.split("Duration:")[1].split(",")[0].strip()
        try:
            h, m, s = stamp.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        except ValueError:
            return None
    return None


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
          max_width: int) -> list[str]:
    lines: list[str] = []
    words = text.split()
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_title(draw: ImageDraw.ImageDraw, title: str, max_width: int,
               max_lines: int = 2) -> tuple[list[str], ImageFont.FreeTypeFont]:
    """Largest title size that still fits in max_lines.

    Two lines rather than three: it keeps the title readable at feed scale and
    leaves the chart panel enough room to run the full width of the cover.
    """
    for size in (136, 124, 112, 100, 90, 80):
        font = _font(_BOLD, size)
        lines = _wrap(draw, title, font, max_width)
        if len(lines) <= max_lines:
            return lines, font
    font = _font(_BOLD, 80)
    return _wrap(draw, title, font, max_width)[:max_lines], font


def _fit_title_wide(draw: ImageDraw.ImageDraw, title: str, max_width: int,
                    max_lines: int = 3) -> tuple[list[str], ImageFont.FreeTypeFont]:
    """Largest title size that fits the 16:9 layout's left column.

    Three lines here, not two: the column is roughly half the width of the
    portrait cover, so insisting on two lines would shrink the type past the
    point of being readable on a browse row.
    """
    for size in (66, 60, 54, 48, 44, 40):
        font = _font(_BOLD, size)
        lines = _wrap(draw, title, font, max_width)
        if len(lines) <= max_lines:
            return lines, font
    font = _font(_BOLD, 40)
    return _wrap(draw, title, font, max_width)[:max_lines], font


def _rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.width - 1, img.height - 1],
                                           radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def build(topic: dict[str, Any], video: Path, out_path: Path,
          settings: dict[str, Any]) -> Path:
    """Compose one 1080x1920 Shorts cover and write it as JPEG."""
    canvas = _gradient(WIDTH, HEIGHT)
    draw = ImageDraw.Draw(canvas)

    pad = 72
    text_width = WIDTH - pad * 2

    # ---- badge ------------------------------------------------------------
    series = topic_series(topic)
    badge_text = playlist_of(series)[0].upper()
    badge_font = _font(_BOLD, 42)
    bw = draw.textlength(badge_text, font=badge_font)
    draw.rounded_rectangle([pad, 104, pad + bw + 64, 104 + 88], radius=44, fill=ACCENT)
    draw.text((pad + 32, 104 + 44), badge_text, font=badge_font,
              fill=BG_BOTTOM, anchor="lm")

    # ---- title ------------------------------------------------------------
    title = str(topic.get("title", "")).strip()
    lines, title_font = _fit_title(draw, title, text_width)
    line_h = int(title_font.size * 1.14)
    y = 268
    for line in lines:
        draw.text((pad, y), line, font=title_font, fill=FG)
        y += line_h

    y += 30
    draw.rectangle([pad, y, pad + 220, y + 11], fill=ACCENT)
    y += 66

    subtitle = str(topic.get("subtitle", "")).strip()
    if subtitle:
        sub_font = _font(_REGULAR, 48)
        for line in _wrap(draw, subtitle, sub_font, text_width)[:2]:
            draw.text((pad, y), line, font=sub_font, fill=MUTED)
            y += int(sub_font.size * 1.28)

    # ---- chart panel: whatever vertical room the text left over ------------
    source_font = _font(_REGULAR, 38)
    panel_top = y + 44
    panel_bottom = HEIGHT - 150
    frame = _grab_frame(video, settings)
    if frame is not None and panel_bottom - panel_top > 200:
        top = int(frame.height * CROP_TOP)
        bottom = int(frame.height * (1 - CROP_BOTTOM))
        chart = frame.crop((0, top, frame.width, bottom))

        avail_w, avail_h = text_width, panel_bottom - panel_top
        # Fill the full cover width, then trim any overflow off the bottom —
        # the top of a bar race is the ranking people actually read.
        scale = avail_w / chart.width
        chart = chart.resize((avail_w, max(1, int(chart.height * scale))), Image.LANCZOS)
        if chart.height > avail_h:
            chart = chart.crop((0, 0, chart.width, avail_h))
        chart = _rounded(chart, 28)
        pos = (pad, panel_top + (avail_h - chart.height) // 2)
        # Accent edge so the panel separates from the background.
        edge = Image.new("RGBA", (chart.width + 8, chart.height + 8), (0, 0, 0, 0))
        ImageDraw.Draw(edge).rounded_rectangle(
            [0, 0, edge.width - 1, edge.height - 1], radius=32,
            outline=ACCENT, width=4)
        canvas.paste(edge, (pos[0] - 4, pos[1] - 4), edge)
        canvas.paste(chart, pos, chart)

    draw.text((pad, HEIGHT - 96), f"Source: {topic.get('source', 'unknown')}",
              font=source_font, fill=MUTED)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "JPEG", quality=92, optimize=True)
    return out_path


def build_wide(topic: dict[str, Any], video: Path, out_path: Path,
               settings: dict[str, Any]) -> Path:
    """Compose the 1280x720 thumbnail YouTube actually displays.

    A re-layout rather than a crop of the portrait cover: cropping to 16:9 would
    lose the title band at the top and the source credit at the bottom, which are
    the two things that make the thumbnail readable at browse scale. Text sits in
    a left column, the real chart frame fills the right.
    """
    canvas = _gradient(WIDE_WIDTH, WIDE_HEIGHT)
    draw = ImageDraw.Draw(canvas)

    pad = 44
    col_w = int(WIDE_WIDTH * 0.50) - pad          # left text column
    chart_x = pad + col_w + 28

    # ---- badge ----
    series = topic_series(topic)
    badge_text = playlist_of(series)[0].upper()
    badge_font = _font(_BOLD, 22)
    bw = draw.textlength(badge_text, font=badge_font)
    draw.rounded_rectangle([pad, pad, pad + bw + 34, pad + 46], radius=23, fill=ACCENT)
    draw.text((pad + 17, pad + 23), badge_text, font=badge_font, fill=BG_BOTTOM, anchor="lm")

    # ---- title block, vertically centred between badge and source ----
    # Measured before drawing: top-aligning it leaves a dead void under short
    # titles, which reads as a broken layout at browse size.
    title = str(topic.get("title", "")).strip()
    lines, title_font = _fit_title_wide(draw, title, col_w)
    line_h = int(title_font.size * 1.13)

    subtitle = str(topic.get("subtitle", "")).strip()
    sub_font = _font(_REGULAR, 26)
    sub_lines = _wrap(draw, subtitle, sub_font, col_w)[:2] if subtitle else []
    sub_h = int(sub_font.size * 1.28)

    block_h = len(lines) * line_h + 14 + 7 + 34 + len(sub_lines) * sub_h
    area_top, area_bottom = pad + 78, WIDE_HEIGHT - 78
    y = area_top + max(0, (area_bottom - area_top - block_h) // 2)

    for line in lines:
        draw.text((pad, y), line, font=title_font, fill=FG)
        y += line_h

    y += 14
    draw.rectangle([pad, y, pad + 130, y + 7], fill=ACCENT)
    y += 34

    for line in sub_lines:
        draw.text((pad, y), line, font=sub_font, fill=MUTED)
        y += sub_h

    draw.text((pad, WIDE_HEIGHT - 52), f"Source: {topic.get('source', 'unknown')}",
              font=_font(_REGULAR, 22), fill=MUTED)

    # ---- chart panel on the right ----
    frame = _grab_frame(video, settings)
    if frame is not None:
        top = int(frame.height * CROP_TOP)
        bottom = int(frame.height * (1 - CROP_BOTTOM))
        chart = frame.crop((0, top, frame.width, bottom))

        avail_w = WIDE_WIDTH - chart_x - pad
        avail_h = WIDE_HEIGHT - pad * 2
        # Fit inside the panel; a vertical chart in a landscape box is height
        # bound, so scale on whichever axis binds first.
        scale = min(avail_w / chart.width, avail_h / chart.height)
        chart = chart.resize((max(1, int(chart.width * scale)),
                              max(1, int(chart.height * scale))), Image.LANCZOS)
        chart = _rounded(chart, 18)
        pos = (chart_x + (avail_w - chart.width) // 2,
               pad + (avail_h - chart.height) // 2)
        edge = Image.new("RGBA", (chart.width + 6, chart.height + 6), (0, 0, 0, 0))
        ImageDraw.Draw(edge).rounded_rectangle(
            [0, 0, edge.width - 1, edge.height - 1], radius=21, outline=ACCENT, width=3)
        canvas.paste(edge, (pos[0] - 3, pos[1] - 3), edge)
        canvas.paste(chart, pos, chart)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "JPEG", quality=92, optimize=True)
    return out_path


def _topics_by_key() -> dict[str, dict[str, Any]]:
    return {str(t.get("key")): t for t in load_topics()}


def _export_root(settings: dict[str, Any]) -> Path:
    try:
        return resolve_path(settings, "export")
    except Exception:
        return PROJECT_ROOT / "export"


def cmd_build(args: argparse.Namespace) -> None:
    settings = load_settings()
    root = _export_root(settings)
    if not root.exists():
        raise SystemExit(f"no export directory at {root}")

    if args.date:
        day = root / args.date
        if not day.exists():
            raise SystemExit(f"no export for {args.date} at {day}")
    else:
        days = sorted(p for p in root.iterdir() if p.is_dir())
        if not days:
            raise SystemExit(f"no export dates under {root}")
        day = days[-1]

    topics = _topics_by_key()
    made, skipped, missing = 0, 0, []

    for series_dir in sorted(p for p in day.iterdir() if p.is_dir()):
        if args.series and series_dir.name != args.series:
            continue
        for folder in sorted(p for p in series_dir.iterdir() if p.is_dir()):
            video = folder / "video.mp4"
            if not video.exists():
                continue
            # Folders are either `<key>` or `<NN>_<key>`.
            key = folder.name.split("_", 1)[1] if folder.name[:2].isdigit() else folder.name
            topic = topics.get(key)
            if topic is None:
                missing.append(folder.name)
                continue
            out_path = folder / "thumbnail.jpg"
            if out_path.exists() and not args.force:
                skipped += 1
                continue
            build(topic, video, out_path, settings)
            made += 1
            build_wide(topic, video, folder / "thumbnail_yt.jpg", settings)
            print(f"  + {series_dir.name}/{folder.name}/thumbnail.jpg + thumbnail_yt.jpg")

    print(f"\n{made} thumbnail(s) written under {day}"
          + (f", {skipped} already existed (use --force to rebuild)" if skipped else ""))
    if missing:
        print(f"no matching topic for: {', '.join(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build YouTube thumbnails for exported videos.")
    parser.add_argument("--date", help="export date folder, e.g. 2026-08-10 (default: newest)")
    parser.add_argument("--series", help="limit to one series folder, e.g. money")
    parser.add_argument("--force", action="store_true", help="rebuild thumbnails that already exist")
    parser.set_defaults(func=cmd_build)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
