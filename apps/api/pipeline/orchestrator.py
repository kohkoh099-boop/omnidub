"""
The orchestrator: stitches ASR → emotion → translate → TTS → mux.

Each run lives in its own temp dir, and emits progress events that the
web UI streams over SSE.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

from . import media, mimo


LANG_NAMES = {
    "zh": "Mandarin Chinese",
    "id": "Bahasa Indonesia",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "es": "Spanish",
    "de": "German",
    "fr": "French",
}


@dataclass
class DubJob:
    src_video: Path
    target_lang: str
    workdir: Path
    burn_subtitles: bool = False
    built_in_voice: str | None = None  # if cloning disabled
    progress: list[dict] = field(default_factory=list)

    def emit(self, stage: str, **kw):
        evt = {"stage": stage, **kw}
        self.progress.append(evt)
        return evt


async def _expected_tts_duration(tts_bytes: bytes) -> float:
    """Approximate the rendered duration from a WAV byte blob."""
    import soundfile as sf
    import io
    with io.BytesIO(tts_bytes) as b:
        info = sf.info(b)
    return info.frames / info.samplerate


async def run_dub(job: DubJob) -> AsyncIterator[dict]:
    """Yields progress events. Final event has {stage:'done', output:<path>}."""

    wd = job.workdir
    wd.mkdir(parents=True, exist_ok=True)

    # 1. Extract 16 kHz mono WAV for ASR + get total duration.
    audio_wav = wd / "source.wav"
    await media.extract_audio(job.src_video, audio_wav, sr=16000)
    total_dur = await media.probe_duration(job.src_video)
    yield job.emit("extract", duration=round(total_dur, 2))

    # 2. ASR + diarization in one MiMo call.
    audio_b64 = media.file_to_b64(audio_wav)
    asr = await mimo.transcribe_audio(audio_b64, mime="audio/wav")
    segs = asr.get("segments", [])
    src_lang = asr.get("language", "auto")
    yield job.emit("transcribe", segments=len(segs), source_lang=src_lang)

    if not segs:
        yield job.emit("error", reason="no speech detected")
        return

    # 3. Build per-speaker voice-clone samples.
    speakers: dict[str, list[dict]] = {}
    for s in segs:
        speakers.setdefault(s["speaker"], []).append(s)

    voice_samples: dict[str, str] = {}  # speaker -> base64 wav
    if not job.built_in_voice:
        for spk, lines in speakers.items():
            # pick the longest clean line
            lines_sorted = sorted(lines, key=lambda l: l["end"] - l["start"], reverse=True)
            for cand in lines_sorted[:3]:
                clip = wd / f"voice_{spk}.wav"
                try:
                    await media.slice_audio(audio_wav, cand["start"], cand["end"], clip)
                    if clip.stat().st_size > 5000:
                        voice_samples[spk] = media.file_to_b64(clip)
                        break
                except Exception:
                    continue
        yield job.emit("voice_clone", speakers=list(voice_samples.keys()))

    # 4. Emotion tag per segment, in parallel (bounded).
    sem = asyncio.Semaphore(4)

    async def tag_one(i: int, seg: dict):
        frame_dir = wd / f"frames_{i}"
        try:
            frame_paths = await media.extract_frames(
                job.src_video, seg["start"], seg["end"], frame_dir, fps=2.0, max_frames=4,
            )
        except Exception:
            frame_paths = []
        frames_b64 = [media.file_to_b64(p) for p in frame_paths[:4]]
        async with sem:
            tag = await mimo.classify_emotion(frames_b64, seg["text"])
        seg["emotion"] = tag
        return tag

    await asyncio.gather(*[tag_one(i, s) for i, s in enumerate(segs)])
    yield job.emit("emotion_tag", tagged=len(segs))

    # 5. Timing-aware translation with up-to-3 retries per segment.
    target_lang_name = LANG_NAMES.get(job.target_lang, job.target_lang)

    async def translate_one(i: int, seg: dict):
        clip_dur = max(0.4, seg["end"] - seg["start"])
        previous = None
        for attempt in range(3):
            t = await mimo.translate_with_timing(
                source_text=seg["text"],
                source_lang=src_lang,
                target_lang=target_lang_name,
                target_duration_sec=clip_dur,
                emotion=seg["emotion"],
                previous=previous,
            )
            seg["translation"] = t["translation"]
            seg["expected_dur"] = t.get("expected_duration_sec", clip_dur)
            # if model claims it already matches, trust it; else iterate
            if abs(seg["expected_dur"] - clip_dur) / clip_dur <= 0.12:
                return
            previous = {"translation": t["translation"], "measured": seg["expected_dur"]}

    # Translate sequentially-ish in small batches to avoid rate bursts.
    for i, seg in enumerate(segs):
        await translate_one(i, seg)
    yield job.emit("translate", segments=len(segs))

    # 6. TTS each segment.
    tts_paths: list[dict] = []
    tts_sem = asyncio.Semaphore(4)

    async def tts_one(i: int, seg: dict):
        async with tts_sem:
            spk = seg["speaker"]
            result = await mimo.synthesize(
                text=seg["translation"],
                emotion=seg["emotion"],
                voice=job.built_in_voice,
                voice_sample_b64=voice_samples.get(spk),
                voice_sample_mime="audio/wav",
                fmt="wav",
            )
        out = wd / f"tts_{i:04d}.wav"
        out.write_bytes(result.audio_bytes)
        tts_paths.append({"path": str(out), "start": seg["start"], "end": seg["end"], "speaker": seg["speaker"]})

    await asyncio.gather(*[tts_one(i, s) for i, s in enumerate(segs)])
    tts_paths.sort(key=lambda x: x["start"])
    yield job.emit("tts", rendered=len(tts_paths))

    # 7. Assemble the dub track at full timeline.
    dub_wav = wd / "dub.wav"
    await media.assemble_dub_track(tts_paths, total_dur, dub_wav, sr=24000)

    # 8. Mux with the source video + optional burned subtitles.
    srt_path = None
    if job.burn_subtitles:
        srt_path = wd / "subs.srt"
        media.write_srt(
            [{"start": s["start"], "end": s["end"], "text": s["translation"]} for s in segs],
            srt_path,
        )

    out_mp4 = wd / "omnidub_output.mp4"
    await media.mux_dub(
        src_video=job.src_video,
        dub_track=dub_wav,
        out_path=out_mp4,
        original_bg_db=-18.0,
        subtitles=srt_path,
    )
    yield job.emit("done", output=str(out_mp4), segments=len(segs), speakers=len(speakers))
