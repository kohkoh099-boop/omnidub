"""
ffmpeg helpers. Thin wrappers around subprocess so the rest of the
pipeline never has to think about command-line flags.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import tempfile
from pathlib import Path


async def _run(*args: str) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out, err


async def probe_duration(path: str | Path) -> float:
    rc, out, _ = await _run(
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path),
    )
    if rc != 0:
        return 0.0
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


async def extract_audio(src: str | Path, dst_wav: str | Path, *, sr: int = 16000) -> None:
    rc, _, err = await _run(
        "ffmpeg", "-y", "-i", str(src),
        "-vn", "-ac", "1", "-ar", str(sr),
        "-sample_fmt", "s16", str(dst_wav),
    )
    if rc != 0:
        raise RuntimeError(f"ffmpeg extract_audio failed: {err.decode(errors='ignore')[:500]}")


async def slice_audio(src_wav: str | Path, start: float, end: float, dst_wav: str | Path) -> None:
    rc, _, err = await _run(
        "ffmpeg", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
        "-i", str(src_wav), "-c", "copy", str(dst_wav),
    )
    if rc != 0:
        raise RuntimeError(f"ffmpeg slice_audio failed: {err.decode(errors='ignore')[:500]}")


async def extract_frames(
    src_video: str | Path,
    start: float,
    end: float,
    dst_dir: str | Path,
    *,
    fps: float = 2.0,
    max_frames: int = 6,
) -> list[Path]:
    dst = Path(dst_dir)
    dst.mkdir(parents=True, exist_ok=True)
    rc, _, err = await _run(
        "ffmpeg", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
        "-i", str(src_video), "-vf", f"fps={fps},scale=320:-1",
        "-frames:v", str(max_frames), str(dst / "frame_%03d.jpg"),
    )
    if rc != 0:
        raise RuntimeError(f"ffmpeg extract_frames failed: {err.decode(errors='ignore')[:500]}")
    return sorted(dst.glob("frame_*.jpg"))


def file_to_b64(path: str | Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


async def mux_dub(
    *,
    src_video: str | Path,
    dub_track: str | Path,
    out_path: str | Path,
    original_bg_db: float = -18.0,
    subtitles: str | Path | None = None,
) -> None:
    """Mux a dub audio track onto the source video, ducking the original.

    The original dialogue is preserved at `original_bg_db` dB so ambience and
    music are not lost. If a subtitles file is provided it is burned in.
    """
    # Duck the original audio to the requested level.
    # Then mix (amix) with the dub track at 0 dB and re-encode.
    filter_complex_parts = [
        f"[0:a]volume={original_bg_db}dB[orig]",
        "[1:a]volume=0dB[dub]",
        "[orig][dub]amix=inputs=2:duration=longest:dropout_transition=0[aout]",
    ]

    vf = "null"
    if subtitles:
        # Escape the path for ffmpeg's filter syntax.
        sub_esc = str(subtitles).replace(":", "\\:").replace("'", "\\'")
        vf = f"subtitles='{sub_esc}':force_style='FontName=Arial,FontSize=18,Outline=2,Shadow=0'"

    rc, _, err = await _run(
        "ffmpeg", "-y",
        "-i", str(src_video),
        "-i", str(dub_track),
        "-filter_complex", ";".join(filter_complex_parts),
        "-map", "0:v",
        "-map", "[aout]",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    )
    if rc != 0:
        raise RuntimeError(f"ffmpeg mux_dub failed: {err.decode(errors='ignore')[:500]}")


async def assemble_dub_track(
    segments: list[dict],
    total_duration: float,
    out_wav: str | Path,
    *,
    sr: int = 24000,
) -> None:
    """Place each TTS segment at its `start` time, padding silence between.

    `segments` = [{"path": str, "start": float, "end": float}, ...]
    """
    import soundfile as sf
    import numpy as np

    total_samples = int(total_duration * sr) + sr  # 1 sec pad
    track = np.zeros(total_samples, dtype=np.float32)

    for seg in segments:
        audio, src_sr = sf.read(seg["path"], dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if src_sr != sr:
            # cheap linear resample
            ratio = sr / src_sr
            new_len = int(len(audio) * ratio)
            xp = np.linspace(0, 1, num=len(audio), endpoint=False)
            fp = audio
            x = np.linspace(0, 1, num=new_len, endpoint=False)
            audio = np.interp(x, xp, fp).astype(np.float32)

        start_sample = int(seg["start"] * sr)
        end_sample = min(start_sample + len(audio), total_samples)
        audio = audio[: end_sample - start_sample]
        # Add (not overwrite) so overlapping speakers blend cleanly.
        track[start_sample:end_sample] += audio

    peak = float(np.max(np.abs(track))) or 1.0
    if peak > 1.0:
        track = track / peak * 0.98

    sf.write(str(out_wav), track, sr, subtype="PCM_16")


def write_srt(segments: list[dict], out_path: str | Path) -> None:
    """Write an SRT from [{start, end, text}, ...]."""
    def ts(t: float) -> str:
        h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
        return f"{h:02d}:{m:02d}:{int(s):02d},{int((s - int(s)) * 1000):03d}"

    with open(out_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            f.write(f"{i}\n{ts(seg['start'])} --> {ts(seg['end'])}\n{seg['text']}\n\n")


def which_or_raise(binary: str) -> str:
    p = shutil.which(binary)
    if not p:
        raise RuntimeError(f"{binary} not found on PATH. Install ffmpeg/ffprobe.")
    return p
