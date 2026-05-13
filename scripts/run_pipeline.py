"""
Run the OmniDub pipeline end-to-end on samples/source_en.mp4 → 中文 dub.
Emits a JSON log of stages + writes dubbed MP4 to samples/dubbed_zh.mp4.
"""
from __future__ import annotations
import asyncio, json, os, sys, time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
from pipeline.orchestrator import DubJob, run_dub  # noqa: E402


async def main():
    root = Path(__file__).resolve().parent.parent
    src = root / "samples" / "source_en.mp4"
    wd = root / "samples" / "_job"
    wd.mkdir(parents=True, exist_ok=True)
    assert src.exists(), f"missing {src}"

    job = DubJob(
        src_video=src,
        target_lang="zh",
        workdir=wd,
        burn_subtitles=True,          # show Chinese subs burned-in for demo
        built_in_voice=None,           # enable voice cloning per speaker
    )

    t0 = time.time()
    timeline = []
    async for evt in run_dub(job):
        elapsed = time.time() - t0
        timeline.append({"t": round(elapsed, 2), **evt})
        print(f"[{elapsed:6.2f}s] {json.dumps(evt, ensure_ascii=False)}")

    # persist timeline
    (root / "samples" / "timeline.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2)
    )
    print(f"\nTotal: {time.time()-t0:.1f}s")
    # move final output
    final_src = Path(timeline[-1].get("output", ""))
    if final_src.exists():
        dst = root / "samples" / "dubbed_zh.mp4"
        dst.write_bytes(final_src.read_bytes())
        print(f"✓ dubbed video → {dst}")


if __name__ == "__main__":
    asyncio.run(main())
