"""Edge TTS speech service for manim-voiceover.

manim-voiceover 0.4.0 ships azure/elevenlabs/gemini/gtts/openai/pyttsx3 backends —
all either paid (API key) or noticeably robotic. Microsoft Edge's neural voices are
free, need no API key, and sound markedly better, so this adds them as a service.

47 English voices are available, including Indian English (en-IN-NeerjaNeural,
en-IN-PrabhatNeural). List them all with:
    python -m graph_bot.scenes.edge_speech --list
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from manim_voiceover._typing import VoiceoverData
from manim_voiceover.helper import remove_bookmarks
from manim_voiceover.services.base import (
    PathLike,
    SpeechService,
    initialize_speech_service,
    path_to_string,
)

DEFAULT_VOICE = "en-US-AriaNeural"


class EdgeService(SpeechService):
    """Free, high-quality neural TTS via Microsoft Edge (no API key)."""

    def __init__(
        self,
        voice: str = DEFAULT_VOICE,
        rate: str = "+0%",
        pitch: str = "+0Hz",
        **kwargs: object,
    ) -> None:
        initialize_speech_service(self, kwargs)
        self.voice = voice
        self.rate = rate
        self.pitch = pitch

    def generate_from_text(
        self,
        text: str,
        cache_dir: PathLike | None = None,
        path: PathLike | None = None,
        **kwargs: object,
    ) -> VoiceoverData:
        if cache_dir is None:
            cache_dir = self.cache_dir

        input_text = remove_bookmarks(text)
        input_data = {
            "input_text": input_text,
            "service": "edge",
            "voice": self.voice,
            "rate": self.rate,
            "pitch": self.pitch,
        }

        cached = self.get_cached_result(input_data, cache_dir)
        if cached is not None:
            return cached

        audio_path = (
            path_to_string(path) if path else self.get_audio_basename(input_data) + ".mp3"
        )
        self._synthesize(input_text, Path(cache_dir) / audio_path)

        return {
            "input_text": text,
            "input_data": input_data,
            "original_audio": audio_path,
        }

    def _synthesize(self, text: str, out_path: Path) -> None:
        import edge_tts

        async def run() -> None:
            comm = edge_tts.Communicate(
                text, self.voice, rate=self.rate, pitch=self.pitch
            )
            await comm.save(str(out_path))

        try:
            asyncio.run(run())
        except RuntimeError:
            # Already inside an event loop (rare under Manim); use a fresh one.
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(run())
            finally:
                loop.close()

        if not out_path.exists() or out_path.stat().st_size == 0:
            raise RuntimeError(
                f"Edge TTS produced no audio for voice {self.voice!r}. "
                "Check the voice name and your internet connection."
            )


def _list_voices() -> None:  # pragma: no cover - CLI helper
    import edge_tts

    voices = asyncio.run(edge_tts.list_voices())
    for v in sorted(voices, key=lambda x: x["ShortName"]):
        if v["Locale"].startswith("en-"):
            print(f"{v['ShortName']:<40} {v['Gender']:<8} {v['Locale']}")


if __name__ == "__main__":  # pragma: no cover
    import sys

    if "--list" in sys.argv:
        _list_voices()
    else:
        print(__doc__)
