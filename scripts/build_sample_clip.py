"""
Build a self-contained demo source clip using MiMo's own TTS as the
"original" audio. Two speakers, English, ~18 seconds. Saved as
samples/source_en.mp4 with a simple title card video.
"""
from __future__ import annotations
import asyncio, base64, os, sys, subprocess, tempfile, json
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
from pipeline import mimo  # noqa: E402


# Two-speaker mini-interview about video dubbing — on-topic for the demo.
SCRIPT = [
    {"speaker": "Host",  "voice": "Chloe",     "emotion": "excited",
     "text": "So, you built a tool that dubs videos into any language — and it actually sounds like the original speaker?"},
    {"speaker": "Guest", "voice": "default_male_01", "emotion": "confident",
     "text": "That's right. Every speaker keeps their voice, their emotion, and the timing of the original shot. No more robotic dubs."},
    {"speaker": "Host",  "voice": "Chloe",     "emotion": "amazed",
     "text": "Wait, emotion too? If someone's whispering or shouting, it carries over?"},
    {"speaker": "Guest", "voice": "default_male_01", "emotion": "playful",
     "text": "Exactly. It's all powered by the Xiaomi MiMo model family, end to end."},
]


async def render():
    out_dir = Path(__file__).resolve().parent.parent / "samples"
    out_dir.mkdir(exist_ok=True)
    wav_paths = []

    for i, line in enumerate(SCRIPT):
        print(f"[{i+1}/{len(SCRIPT)}] TTS {line['speaker']:<5} ({line['emotion']}) — {line['text'][:60]}…")
        # Try voice then fallback to Chloe if unknown
        voices_to_try = [line["voice"], "Chloe"]
        for v in voices_to_try:
            try:
                res = await mimo.synthesize(
                    text=line["text"],
                    emotion=line["emotion"],
                    voice=v,
                    fmt="wav",
                )
                break
            except Exception as e:
                print(f"       voice={v} failed: {e}")
                continue
        p = out_dir / f"line_{i:02d}_{line['speaker']}.wav"
        p.write_bytes(res.audio_bytes)
        wav_paths.append(p)
        print(f"       → {p.name} ({len(res.audio_bytes)/1024:.1f} KB)")

    # Concatenate with 0.35s silence between lines
    pause_wav = out_dir / "_pause.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    "anullsrc=r=24000:cl=mono", "-t", "0.35", str(pause_wav)],
                   check=True, capture_output=True)

    concat_list = out_dir / "_concat.txt"
    with concat_list.open("w") as f:
        for i, p in enumerate(wav_paths):
            f.write(f"file '{p.resolve()}'\n")
            if i < len(wav_paths) - 1:
                f.write(f"file '{pause_wav.resolve()}'\n")

    combined_wav = out_dir / "source_en.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(concat_list), "-c", "copy", str(combined_wav)],
                   check=True, capture_output=True)
    print(f"combined wav → {combined_wav}")

    # Measure total duration
    dur = float(subprocess.check_output([
        "ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=nw=1:nk=1", str(combined_wav)]).decode().strip())
    print(f"total duration: {dur:.2f}s")

    # Create a simple title-card video frame (1280x720) and loop as source video
    card = out_dir / "_card.png"
    subprocess.run(["ffmpeg", "-y",
        "-f","lavfi","-i","color=c=0x0b0d12:s=1280x720:d=1",
        "-vf", (
            "drawtext=text='The OmniDub Interview':fontcolor=white:fontsize=56:"
                "x=(w-text_w)/2:y=200:"
                "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf,"
            "drawtext=text='Two speakers · English · 18s':fontcolor=0x98a0b3:fontsize=28:"
                "x=(w-text_w)/2:y=300:"
                "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf,"
            "drawtext=text='[sample clip for dubbing demo]':fontcolor=0xff6b35:fontsize=24:"
                "x=(w-text_w)/2:y=440:"
                "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),
        "-frames:v", "1", str(card)], check=True, capture_output=True)

    source_mp4 = out_dir / "source_en.mp4"
    subprocess.run(["ffmpeg","-y",
        "-loop","1","-i", str(card),
        "-i", str(combined_wav),
        "-c:v","libx264","-preset","veryfast","-tune","stillimage",
        "-pix_fmt","yuv420p","-r","24",
        "-c:a","aac","-b:a","192k",
        "-shortest", str(source_mp4)], check=True, capture_output=True)
    print(f"source video → {source_mp4}")

    # Cleanup
    for p in wav_paths + [pause_wav, concat_list, card, combined_wav]:
        try: p.unlink()
        except Exception: pass
    print("DONE")


if __name__ == "__main__":
    asyncio.run(render())
