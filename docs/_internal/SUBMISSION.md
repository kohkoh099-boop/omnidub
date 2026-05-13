# Xiaomi MiMo Orbit 100T — Submission Copy

Paste-ready text for the application form at https://100t.xiaomimimo.com.

---

## Project name
OmniDub — Emotion-aware Video Auto-Dubbing Studio

## One-liner (中文 + EN)

**中文：** OmniDub 是一款开源的情感感知视频自动配音工具，完全基于 Xiaomi MiMo-V2.5 全家桶构建。上传视频，选择目标语言，输出的配音保留每位说话人的音色、情绪与时长节奏。

**English:** OmniDub is an open-source, emotion-aware video auto-dubbing tool built end-to-end on the Xiaomi MiMo-V2.5 family. Upload a clip, pick a target language, and every speaker's voice identity, emotional delivery, and shot timing survive the translation.

## AI tools used
- Xiaomi MiMo-V2.5 (audio understanding, video understanding)
- Xiaomi MiMo-V2.5-Pro (reasoning — timing-aware translator)
- Xiaomi MiMo-V2.5-TTS (built-in voices, inline emotion tags)
- Xiaomi MiMo-V2.5-TTS-VoiceClone (per-speaker voice fingerprinting)

No other ML models. No Whisper, no ElevenLabs, no pyannote.

## Project description (detailed)

**Problem.** Today's auto-dubbing tools sound robotic because they lose
three things in translation: emotion (angry lines come out neutral),
voice identity (every speaker is flattened into one narrator), and
timing (dubbed lines run over the next cut).

**Solution.** OmniDub solves each of these using a capability unique to
the MiMo-V2.5 stack:

1. **Emotion preserved** — Per-segment facial expression is classified
   by MiMo-V2.5 vision understanding and piped into MiMo-V2.5-TTS's
   native natural-language control syntax `(angry)…text…`,
   `(whispering)…text…`, `(sighing)…text…`. The emotion is a first-class
   input to the synthesizer, not a post-processing hack.

2. **Voice identity preserved** — The longest clean clip of each
   speaker is extracted, base64-encoded, and passed to
   `mimo-v2.5-tts-voiceclone` as that speaker's voice handle. Three
   speakers in the source means three distinct voices in the dub.

3. **Timing preserved** — MiMo-V2.5-Pro (reasoning model) translates
   each line with the target clip duration as a hard constraint, and
   self-corrects up to 3× if the first draft would be too long or too
   short. Calm lines are budgeted at ~2.5 syllables/sec, shouting at
   ~3.2, whispering at −15%.

**Pipeline:**
`ffmpeg extract → MiMo-V2.5 ASR/diarize → voice-clone fingerprint →
MiMo-V2.5 emotion classify → MiMo-V2.5-Pro timing-aware translate →
MiMo-V2.5-TTS-VoiceClone render → ffmpeg mux with −18 dB ambience bed`

**Scope.** Supports 8 target-language presets (中文, Bahasa Indonesia,
English, 日本語, 한국어, Español, Deutsch, Français). Source language is
autodetected. 2-minute clips complete in ~1× realtime. Single command
install: `docker compose up`.

**Tech stack.** FastAPI (Python 3.12), vanilla HTML/CSS/JS mobile-first
UI, ffmpeg, numpy, soundfile. Open-source, MIT.

## Proof material

- GitHub repo: <PASTE_GITHUB_URL_HERE>
- Live demo video: <PASTE_YOUTUBE_OR_BILIBILI_URL>
- Architecture doc: <GITHUB_URL>/blob/main/docs/ARCHITECTURE.md
- One-click install: `docker compose up --build`

## Why this deserves a higher tier

- **Depth of MiMo integration.** Four distinct MiMo-V2.5 models are
  used, each for the task it's best at. Every node in the dataflow
  touches the MiMo API. This is not a thin wrapper around one
  endpoint.
- **Uses a capability no competitor has.** MiMo-V2.5-TTS's native
  natural-language emotion control (`(angry)…`, `(whispering)…`) is
  the only TTS on the market with this. OmniDub is built around
  exploiting it.
- **Immediately useful.** Content creators translating short-form
  video for Douyin / TikTok / YouTube Shorts can ship dubbed versions
  in minutes. This is the exact "AI-driven creator" profile the 100T
  program is looking for.
- **Reproducible.** One-command install, fully open-source, MIT
  license, dual-language docs.

## Contact

- Email (for 权益 delivery): `<YOUR_EMAIL_HERE>`
- GitHub: `<YOUR_GITHUB_HERE>`
- Xiaomi ID bound email: make sure this matches the application email
