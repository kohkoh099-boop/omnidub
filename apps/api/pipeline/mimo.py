"""
OmniDub — MiMo client wrappers.

All calls hit https://api.xiaomimimo.com/v1 via OpenAI-compatible Chat Completions.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
MIMO_API_KEY = os.getenv("MIMO_API_KEY", "")
HTTP_TIMEOUT = httpx.Timeout(120.0, connect=15.0)


def _headers() -> dict[str, str]:
    if not MIMO_API_KEY:
        raise RuntimeError("MIMO_API_KEY is not set. Put it in .env")
    return {
        "Authorization": f"Bearer {MIMO_API_KEY}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Chat / reasoning
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30))
async def chat(
    model: str,
    messages: list[dict[str, Any]],
    *,
    response_format: dict | None = None,
    temperature: float = 0.4,
    max_tokens: int = 2048,
) -> str:
    """Return the assistant text from a Chat Completions call."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as cx:
        r = await cx.post(f"{MIMO_BASE_URL}/chat/completions", headers=_headers(), json=payload)
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Audio understanding (ASR + diarization)
# ---------------------------------------------------------------------------

ASR_SYSTEM_PROMPT = """You are a precise audio transcription + diarization engine.

Return STRICT JSON, no markdown fences, with this schema:
{
  "language": "ISO 639-1 code of the dominant spoken language",
  "segments": [
    {
      "speaker": "S1" | "S2" | ...,
      "start": 0.00,
      "end":   1.84,
      "text":  "what was said",
      "prosody": "brief label e.g. 'flat', 'rising', 'shouting', 'whispering'"
    }
  ]
}

Rules:
- Group consecutive same-speaker sentences into one segment only if they land in
  the same breath group (< 400 ms gap). Otherwise split.
- Use S1/S2/S3 labels consistently — the same speaker keeps the same label
  throughout.
- start/end are seconds, 2 decimals.
- No overlapping segments. If two people talk at once, pick the louder one.
- Never invent words. If unintelligible, write "[inaudible]".
"""


async def transcribe_audio(audio_b64: str, mime: str = "audio/wav") -> dict:
    """Run ASR + diarization on a base64-encoded audio clip. Returns parsed dict."""
    messages = [
        {"role": "system", "content": ASR_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "input_audio", "input_audio": {"data": audio_b64, "format": mime.split("/")[-1]}},
                {"type": "text", "text": "Transcribe and diarize this clip. Return the JSON."},
            ],
        },
    ]
    raw = await chat("mimo-v2.5", messages, response_format={"type": "json_object"}, temperature=0.1, max_tokens=8000)
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Video emotion tagging
# ---------------------------------------------------------------------------

EMOTION_SYSTEM = """You are a film performance coach. Given a sequence of frames
covering a single spoken line, return exactly ONE tag describing the speaker's
delivery, drawn from this controlled vocabulary:

neutral, happy, sad, angry, fearful, excited, tender, whispering, shouting,
sighing, sarcastic, urgent, tired, playful, crying

Return only the tag, lowercase, no punctuation, no explanation."""


async def classify_emotion(frames_b64: list[str], text_hint: str) -> str:
    """Classify the speaker's emotion in the given frames."""
    if not frames_b64:
        return "neutral"
    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": f"The speaker says: \u201c{text_hint}\u201d. Classify the delivery."},
    ]
    for f in frames_b64[:6]:  # keep context small
        user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{f}"}})

    messages = [
        {"role": "system", "content": EMOTION_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    try:
        tag = (await chat("mimo-v2.5", messages, temperature=0.2, max_tokens=20)).strip().lower().split()[0]
        allowed = {"neutral","happy","sad","angry","fearful","excited","tender","whispering","shouting","sighing","sarcastic","urgent","tired","playful","crying"}
        return tag if tag in allowed else "neutral"
    except Exception:
        return "neutral"


# ---------------------------------------------------------------------------
# Timing-aware translator
# ---------------------------------------------------------------------------

TRANSLATOR_SYSTEM = """You are an expert dubbing translator. Your job is to
translate a line of dialogue so that when spoken in the target language, it
lasts *approximately the same amount of time* as the original.

You will be given:
- source_text, source_lang, target_lang
- target_duration_sec (the clip length the dub must fit in)
- emotion tag (the delivery — keep the feel, not the literal words)
- previous draft + its measured duration, if this is a retry

Rules:
1. Preserve meaning and tone, not literal word count.
2. If the target language is Mandarin, budget ~4 characters per second of calm
   delivery, ~5 for fast delivery.
3. If the target language is Indonesian/English, budget ~2.5 syllables per second
   calm, ~3.2 fast.
4. Emotion tag `shouting` or `urgent` allows up to +20% speed; `whispering` or
   `tender` requires −15%.
5. Do NOT add stage directions, brackets, or narration — the emotion tag is
   applied separately by the TTS engine.
6. Return STRICT JSON: {"translation": "...", "expected_duration_sec": 0.00}.
"""


async def translate_with_timing(
    *,
    source_text: str,
    source_lang: str,
    target_lang: str,
    target_duration_sec: float,
    emotion: str,
    previous: dict | None = None,
) -> dict:
    user = {
        "source_text": source_text,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "target_duration_sec": round(target_duration_sec, 2),
        "emotion": emotion,
    }
    if previous:
        user["previous_draft"] = previous.get("translation")
        user["previous_measured_duration_sec"] = previous.get("measured")
        user["feedback"] = (
            "Previous draft was too LONG — shorten." if previous.get("measured", 0) > target_duration_sec * 1.08
            else "Previous draft was too SHORT — expand." if previous.get("measured", 0) < target_duration_sec * 0.92
            else "Previous draft was fine — polish."
        )

    messages = [
        {"role": "system", "content": TRANSLATOR_SYSTEM},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]
    raw = await chat("mimo-v2.5-pro", messages, response_format={"type": "json_object"}, temperature=0.5, max_tokens=800)
    return json.loads(raw)


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

@dataclass
class TTSResult:
    audio_bytes: bytes
    format: str
    sample_rate: int


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=20))
async def synthesize(
    *,
    text: str,
    emotion: str,
    voice: str | None = None,
    voice_sample_b64: str | None = None,
    voice_sample_mime: str = "audio/wav",
    fmt: str = "wav",
) -> TTSResult:
    """Render a single line of dubbed speech.

    If `voice_sample_b64` is given, uses voice cloning.
    Else if `voice` is given, uses that built-in voice.
    Else falls back to the default voice.
    """
    if voice_sample_b64:
        model = "mimo-v2.5-tts-voiceclone"
        voice_handle = f"data:{voice_sample_mime};base64,{voice_sample_b64}"
    else:
        model = "mimo-v2.5-tts"
        voice_handle = voice or "Chloe"

    # Prefix the emotion as an inline audio tag. MiMo TTS docs confirm
    # "(Emotion)Content" is the supported bracket format.
    styled = f"({emotion}){text}" if emotion and emotion != "neutral" else text

    messages = [
        {"role": "user", "content": f"Deliver the line with a {emotion} tone, natural pace, preserving any tags."},
        {"role": "assistant", "content": styled},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "audio": {"format": fmt, "voice": voice_handle},
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as cx:
        r = await cx.post(f"{MIMO_BASE_URL}/chat/completions", headers=_headers(), json=payload)
        r.raise_for_status()
        data = r.json()

    # The TTS response places the audio under choices[0].message.audio.data
    # as base64. See docs: "Speech synthesis (MiMo-V2.5-TTS Series)".
    msg = data["choices"][0]["message"]
    audio_b64 = msg["audio"]["data"] if isinstance(msg.get("audio"), dict) else msg.get("audio")
    if not audio_b64:
        raise RuntimeError(f"TTS response missing audio: {data}")

    return TTSResult(
        audio_bytes=base64.b64decode(audio_b64),
        format=fmt,
        sample_rate=24000,
    )


async def synthesize_many(jobs: list[dict]) -> list[TTSResult]:
    """Render several TTS jobs concurrently (bounded)."""
    sem = asyncio.Semaphore(4)

    async def _one(job):
        async with sem:
            return await synthesize(**job)

    return await asyncio.gather(*[_one(j) for j in jobs])
