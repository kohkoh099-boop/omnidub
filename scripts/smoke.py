"""
Smoke test — exercises the real MiMo Token Plan endpoints to verify each
capability OmniDub relies on.
"""
from __future__ import annotations
import asyncio, base64, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "apps/api"))

from pipeline import mimo  # noqa: E402


async def test_chat():
    out = await mimo.chat(
        "mimo-v2.5-pro",
        [{"role": "user", "content": "Reply with exactly one word: pong"}],
        temperature=0.1, max_tokens=50,
    )
    print(f"[chat]       mimo-v2.5-pro  → {out!r}")
    assert "pong" in out.lower()


async def test_tts_builtin():
    res = await mimo.synthesize(
        text="Hello, this is a test of MiMo speech synthesis.",
        emotion="excited",
        voice="Chloe",
        fmt="wav",
    )
    out = "/tmp/omnidub_smoke_builtin.wav"
    with open(out, "wb") as f:
        f.write(res.audio_bytes)
    print(f"[tts-builtin] saved {len(res.audio_bytes)} bytes → {out}")
    assert len(res.audio_bytes) > 5000


async def test_translate_with_timing():
    out = await mimo.translate_with_timing(
        source_text="I can't believe we actually pulled this off!",
        source_lang="en",
        target_lang="Mandarin Chinese",
        target_duration_sec=2.4,
        emotion="excited",
    )
    print(f"[translate]   {json.dumps(out, ensure_ascii=False)}")
    assert "translation" in out


async def main():
    print("=" * 60)
    print(f"MIMO_BASE_URL = {mimo.MIMO_BASE_URL}")
    print(f"MIMO_API_KEY  = {mimo.MIMO_API_KEY[:6]}…{mimo.MIMO_API_KEY[-4:]}" if mimo.MIMO_API_KEY else "(empty)")
    print("=" * 60)

    for test in [test_chat, test_translate_with_timing, test_tts_builtin]:
        t0 = time.time()
        try:
            await test()
            print(f"        ✓ {test.__name__}  ({time.time()-t0:.2f}s)\n")
        except Exception as e:
            import traceback
            print(f"        ✗ {test.__name__}: {e}")
            traceback.print_exc()
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
