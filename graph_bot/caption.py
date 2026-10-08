"""Build clickable titles and rich descriptions for each video.

- build_title:       short, curiosity-driven YouTube/Shorts title (<=100 chars).
- build_description: headline + source credit + subscribe CTA + engagement
                     prompt + hashtags (used as the video description / caption).

Per-topic titles come from the topic's `yt_title` (if set in topics.yaml),
otherwise from the curated map below, otherwise the topic's plain title.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

TITLE_MAX = 100

# Curated, clickable default titles by topic key ({range} -> year span).
YT_TITLES: dict[str, str] = {
    "population": "Which Country Has the MOST People? ({range}) 🌍",
    "gdp": "The World's Biggest Economies ({range}) 💰",
    "tourists": "Most Visited Countries on Earth ✈️ ({range})",
    "mobile": "How Phones Took Over the World 📱 ({range})",
    "co2": "Who Emits the Most CO₂? 🏭 ({range})",
    "life_expectancy": "Where Do People Live the Longest? ⏳ ({range})",
    "world_population": "How Fast Is the World Growing? 🌍 ({range})",
    "developers": "Countries With the Most Software Developers 👨‍💻",
    "military": "Who Spends the MOST on Military? 💥 ({range})",
    "air_passengers": "Which Country Flies the Most? ✈️ ({range})",
    "patents": "The Countries Inventing the Future 💡 ({range})",
    "science": "Who Publishes the Most Science? 🔬 ({range})",
    "exports": "The World's Biggest Exporters 📦 ({range})",
    "forest": "Countries With the Most Forest 🌲 ({range})",
    "migrants": "Where Do the World's Migrants Live? 🌍 ({range})",
    "electricity": "Who Generates the Most Electricity? ⚡ ({range})",
    "meat": "The World's Biggest Meat Producers 🍖 ({range})",
    "co2_per_capita": "The REAL Biggest Polluters (Per Person) 🏭 Surprising!",
    "military_personnel": "The World's Biggest Armies 🪖 ({range})",
    # AI / tech pillar
    "ai_compute": "How Much Compute Does AI Training Use? 🤖 ({range})",
    "ai_orgs": "Who Builds the Most AI Models? 🤖 ({range})",
    "ai_countries": "The AI Superpowers 🌍 ({range})",
    "ai_params": "How BIG Are AI Models? 🧠 ({range})",
    "ai_cost": "The Insane Cost of Training AI 💸 ({range})",
    "ai_boom": "The AI Explosion, Visualized 🚀 ({range})",
    "ai_clusters_country": "Which Country Has the Most AI Supercomputers? 🌍",
    "ai_cluster_owners": "Who Actually Owns the AI Compute? 🖥️ ({range})",
    "ai_datacenter_power": "How Much Power Does AI Use? ⚡ ({range})",
    "ai_chip_speed": "How Fast Have AI Chips Gotten? 🚀 ({range})",
    "ai_gpu_count": "It Takes 200,000+ GPUs to Train One AI 🤯 ({range})",
    "ai_cluster_cost": "The Most Expensive Computer Ever Built 💰 ({range})",
    "ai_cluster_chips": "The Biggest AI Supercomputer on Earth 🖥️ ({range})",
    "ai_open_vs_closed": "Open vs Closed: Who's Winning AI? 🤖 ({range})",
    "ai_training_time": "How Long Does It Take to Train an AI? ⏳ ({range})",
    # India in Data pillar
    "india_vs_china_population": "India Just Overtook China 🇮🇳🇨🇳 ({range})",
    "india_vs_china_gdp": "India vs China: The Economy 🇮🇳🇨🇳 ({range})",
    "india_vs_china_life": "India vs China: Who Lives Longer? 🇮🇳🇨🇳",
    "india_vs_china_internet": "India vs China: Getting Online 🌐 ({range})",
    "india_gdp": "India's Economy: 50 Years in 30 Seconds 🇮🇳",
    "india_internet": "How India Got Online 🌐 ({range})",
    "india_mobile": "India's Mobile Revolution 📱 ({range})",
    "india_life": "India's Life Expectancy Transformed 🇮🇳 ({range})",
    # How Charts Lie pillar
    "lie_truncated_axis": "This Chart Grew 200%… or 2%? 📊 Charts Lie #1",
    # Money & cost of living pillar
    "money_gdp_per_capita": "The Richest Countries Per Person 💰 ({range})",
    "money_inflation": "Where Prices Exploded 📈 ({range})",
    "money_unemployment": "Highest Unemployment in the World 📉 ({range})",
    "money_inequality": "The Most Unequal Countries ⚖️ ({range})",
    "money_remittances": "Who Sends the Most Money Home? 💸 ({range})",
    "money_poverty": "Extreme Poverty Is Falling 📉 ({range})",
    "money_spending": "Who Spends the Most? 🛒 ({range})",
    "money_stock_markets": "The World's Biggest Stock Markets 📈 ({range})",
    "money_reserves": "Who Has the Biggest Piggy Bank? 💰 ({range})",
    "money_hightech_exports": "Who Exports the Most Technology? 💻 ({range})",
    "money_fdi": "Where Does the World's Money Go? 💸 ({range})",
    # Biggest-in-the-world totals + football (added 2026-10-08)
    "oil_production": "Who Pumps the Most Oil on Earth? 🛢️ ({range})",
    "coal_production": "Who Digs the Most Coal? ⛏️ ({range})",
    "solar_capacity": "Who Has the Most Solar Power? ☀️ ({range})",
    "wind_power": "Who Makes the Most Wind Power? 🌬️ ({range})",
    "nuclear_power": "Who Makes the Most Nuclear Energy? ⚛️ ({range})",
    "ev_sales": "Who Buys the Most Electric Cars? 🚗 ({range})",
    "rice_production": "India Just Overtook China in Rice 🍚 ({range})",
    "milk_production": "The World's Biggest Milk Producers 🥛 ({range})",
    "gas_production": "Who Produces the Most Natural Gas? 🔥 ({range})",
    "manufacturing_output": "Who Makes the World's Stuff? 🏭 ({range})",
    "football_world_cup_goals": "Brazil vs Germany: Most World Cup Goals ⚽ ({range})",
    "football_euro_wins": "Who Wins the Most at the Euros? ⚽ ({range})",
    "football_copa_wins": "Who Rules the Copa América? 🏆 ({range})",
    # Country vs Country (added 2026-10-08)
    "vs_us_china_economy": "US vs China: Whose Economy Is Really Bigger? 🇺🇸🇨🇳 ({range})",
    "vs_us_china_science": "China Overtook the US in Science 🇺🇸🇨🇳 ({range})",
    "vs_india_uk_gdp": "India vs UK: Whose Economy Is Bigger? 🇮🇳🇬🇧 ({range})",
    "vs_germany_japan_gdp": "Germany Just Overtook Japan 🇩🇪🇯🇵 ({range})",
    "vs_india_pakistan_income": "India vs Pakistan: Who's Richer Per Person? 🇮🇳🇵🇰 ({range})",
    "vs_uk_france_gdp": "UK vs France: The Economy, Head to Head 🇬🇧🇫🇷 ({range})",
    # Concepts pillar
    "gradient_descent": "AI Learns by Falling Downhill ⛰️ | ML Basics",
    "simpsons_paradox": "Every Group Went Down. The Total Went Up. 📊",
    "kmeans": "Nobody Told It These Were Groups 🤖 | ML Basics",
    # ML Basics series
    "ml_what_is": "What Is Machine Learning? | ML Basics #1 🤖",
    "ml_overfitting": "Why Smart Models Fail | Overfitting | ML Basics #2 📉",
    "ml_train_test": "The #1 Mistake Beginners Make | ML Basics #3 ⚠️",
    "ml_features_labels": "Features vs Labels Explained | ML Basics #4 📊",
    "ml_supervised": "Supervised vs Unsupervised | ML Basics #5 🤖",
    "ml_class_vs_reg": "Classification vs Regression | ML Basics #6 🎯",
    "ml_loss": "How a Model Knows It's Wrong | ML Basics #7 📉",
    "ml_train_infer": "Training vs Inference | ML Basics #8 ⚡",
    "ml_bias_variance": "Bias vs Variance Explained | ML Basics #9 ⚖️",
    "ml_accuracy_lies": "99% Accurate and Totally Useless | ML Basics #10 🚨",
}


def build_title(topic: dict[str, Any], year_min: int, year_max: int, *, shorts: bool = True) -> str:
    key = topic.get("key", "")
    template = topic.get("yt_title") or YT_TITLES.get(key) or topic.get("title", "World Statistics")
    if year_min and year_max:
        title = template.replace("{range}", f"{year_min}–{year_max}")
    else:
        # Concept scenes have no year range — drop the placeholder cleanly.
        title = template.replace(" ({range})", "").replace("({range})", "").replace("{range}", "")
        title = " ".join(title.split())
    if shorts and "#shorts" not in title.lower():
        candidate = f"{title} #Shorts"
        title = candidate if len(candidate) <= TITLE_MAX else title
    return title[:TITLE_MAX]


_CREDITS_FILE = "CREDITS.yaml"


def music_credit(track: str | None) -> str | None:
    """One-line credit for the track a video was scored with.

    Generated tracks are original to the channel, so they get a plain statement
    rather than an attribution. Folder tracks are looked up in
    ``assets/music/CREDITS.yaml``; an unlisted track still gets a credit line
    built from its filename, so forgetting an entry never silently drops it.
    """
    if not track:
        return None
    # Generated themes are named "<topic-key>-<mood>.wav" and live in the cache.
    if track.lower().endswith(".wav") and "-" in track:
        return "Original score, composed for this video 🎧"

    from .config import PROJECT_ROOT  # local import keeps caption.py import-light

    stem = Path(track).stem
    entry: dict[str, Any] = {}
    path = PROJECT_ROOT / "assets" / "music" / _CREDITS_FILE
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            entry = data.get(stem) or data.get(track) or {}
        except yaml.YAMLError:
            entry = {}

    name = entry.get("title") or stem.replace("-", " ").replace("_", " ").strip()
    parts = [f'"{name}"']
    if entry.get("artist"):
        parts.append(f"by {entry['artist']}")
    if entry.get("license"):
        parts.append(f"({entry['license']})")
    if entry.get("url"):
        parts.append(f"— {entry['url']}")
    return " ".join(parts)


def build_description(topic: dict[str, Any], year_min: int, year_max: int,
                      music: str | None = None) -> str:
    title = topic.get("title", "")
    subtitle = topic.get("subtitle", "")
    source = topic.get("source", "public data")
    hashtags = list(topic.get("hashtags", []))
    if "shorts" not in [h.lower() for h in hashtags]:
        hashtags = hashtags + ["Shorts"]

    headline = title if not subtitle else f"{title} — {subtitle}"
    tags = " ".join(f"#{h.lstrip('#')}" for h in hashtags)
    blurb = (f"{year_min}–{year_max}, animated. Watch how the world changed. 📈"
             if year_min and year_max else "Explained visually in 30 seconds. 📈")

    lines = [
        headline,
        blurb,
        "",
        f"📊 Data source: {source}",
    ]
    credit = music_credit(music)
    if credit:
        lines.append(f"🎵 Music: {credit}")
    lines += [
        "🔔 A new world-data short every day — subscribe for more!",
        "💬 Which one surprised you? Let me know 👇",
        "",
        tags,
    ]
    return "\n".join(lines).strip() + "\n"


# Backwards-compatible alias (older callers used build_caption).
def build_caption(topic: dict[str, Any], year_min: int, year_max: int,
                  music: str | None = None) -> str:
    return build_description(topic, year_min, year_max, music)
