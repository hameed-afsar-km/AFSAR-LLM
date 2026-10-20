import logging
import re
from typing import AsyncGenerator
import edge_tts
from config import settings

logger = logging.getLogger("afsar.tts")

VOICE = settings.TTS_VOICE
RATE = settings.TTS_RATE
PITCH = settings.TTS_PITCH


def split_sentences(text: str, max_len: int = 160) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    chunks: list[str] = []
    for sentence in sentences:
        if len(sentence) <= max_len:
            chunks.append(sentence)
            continue
        parts = [p.strip() for p in re.split(r"(?<=[,;:])\s+", sentence) if p.strip()]
        piece = ""
        for part in parts:
            if not piece:
                piece = part
            elif len(piece) + len(part) + 1 <= max_len:
                piece = f"{piece} {part}"
            else:
                chunks.append(piece)
                piece = part
        if piece:
            chunks.append(piece)
    return chunks


async def stream_sentence_audio(text: str) -> AsyncGenerator[bytes, None]:
    for sentence in split_sentences(text):
        try:
            communicate = edge_tts.Communicate(sentence, settings.TTS_VOICE, rate=settings.TTS_RATE, pitch=settings.TTS_PITCH)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]
        except Exception as e:
            logger.warning(f"Error streaming sentence audio: {e}")


async def stream_tts(text: str) -> AsyncGenerator[bytes, None]:
    try:
        communicate = edge_tts.Communicate(text, settings.TTS_VOICE, rate=settings.TTS_RATE, pitch=settings.TTS_PITCH)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]
    except Exception as e:
        logger.warning(f"Error streaming TTS: {e}")

