# OmniDub 🎬

> Emotion-aware video auto-dubbing studio, powered by **Xiaomi MiMo-V2.5**.
> Upload a video, pick a target language, get back a dubbed video where every
> speaker keeps their voice, their emotion, and the timing of the original.

Built for the [Xiaomi MiMo Orbit 100T Creator Program](https://100t.xiaomimimo.com).

---

## Why OmniDub is different

Most auto-dubbing tools today sound robotic because they lose three things in translation:

1. **Emotion** — the original speaker is angry, the dub sounds neutral.
2. **Voice identity** — every speaker comes out sounding like the same AI.
3. **Timing** — translated line is too long, so it talks over the next shot.

OmniDub fixes all three by exploiting capabilities that are unique to the MiMo-V2.5 stack:

| Problem | How OmniDub solves it | MiMo feature used |
|---|---|---|
| Flat emotion | Per-sentence emotion detection from facial expression + voice prosody is injected as MiMo's natural-language audio tags: `(angry)`, `(whispering)`, `(sighing)`, `(excited)` | `mimo-v2.5` video understanding + `mimo-v2.5-tts` natural-language control |
| Same-voice speakers | Each speaker's original voice is cloned from their own clip and used only for that speaker's lines | `mimo-v2.5-tts-voiceclone` |
| Off-tempo dub | Reasoning model rewrites the translation until its spoken duration matches the original clip ±8% | `mimo-v2.5-pro` reasoning |
| Ugly lip mismatch | Vowel-shape hinting: the translator is told which Indonesian/Chinese syllables to prefer at each lip-open moment | `mimo-v2.5-pro` + video understanding |
| Setup friction | One `docker compose up`, one web form, no CLI | — |

---

## Demo

**▶️ [Watch the 62-second demo video](https://kohkoh099-boop.github.io/omnidub/#demo)** — see the full pipeline end-to-end.

![screenshot](docs/assets/omnidub_demo.mp4)

Upload a clip → pick target language → wait ~1× realtime → download. That's it.

```bash
git clone https://github.com/your-handle/omnidub
cd omnidub
cp .env.example .env           # drop your MIMO_API_KEY in
docker compose up --build
open http://localhost:8080
```

---

## Architecture

```
  ┌──────────────┐    ┌─────────────────────────────────────────────────┐
  │  Web (HTML)  │───▶│              FastAPI orchestrator                │
  └──────────────┘    │                                                 │
                      │  ffmpeg ─► ASR ─► diarize ─► video-emotion ─►   │
                      │  translate-with-timing ─► TTS (per speaker)     │
                      │  ─► mux ─► MP4                                  │
                      └─────────────────────────────────────────────────┘
                                 │
                                 ▼
                       api.xiaomimimo.com/v1
                       ├─ mimo-v2.5              (audio + video understanding)
                       ├─ mimo-v2.5-pro          (timing-aware translator)
                       ├─ mimo-v2.5-tts-voiceclone
                       └─ mimo-v2.5-tts          (fallback built-in voices)
```

Every arrow is a real call — no local models, no third-party APIs, no hidden
dependencies. The only external brain in the whole pipeline is MiMo.

---

## Pipeline stages

1. **Extract** — `ffmpeg` pulls 16 kHz mono audio and 1 fps keyframe strips.
2. **ASR + diarization** — MiMo-V2.5 audio-understanding returns segments with
   `speaker_id`, `text`, `start`, `end`.
3. **Emotion tag** — for each segment, MiMo-V2.5 inspects the keyframe strip
   that overlaps the time window and returns a tag in
   `{neutral, happy, sad, angry, fearful, excited, tender, whispering, shouting, sighing}`.
4. **Voice fingerprint** — the longest clean clip per speaker is base64-encoded
   and cached as that speaker's `voice` handle for TTS cloning.
5. **Timing-aware translate** — MiMo-V2.5-Pro is given
   `(source_text, target_lang, original_duration, expected_syllables_per_second)`
   and asked to return Chinese/Indonesian/Japanese text of the right length.
   If the first draft is too long/short, it retries up to 3× with explicit
   duration feedback.
6. **TTS** — each segment is rendered with that speaker's cloned voice,
   prefixed with the emotion tag, at 24 kHz.
7. **Mux** — dubbed track is time-aligned, original dialogue is ducked but
   kept at −18 dB for ambience, final MP4 exported with burned subtitles
   (optional).

---

## Supported pairs

Source language: autodetected by MiMo-V2.5 audio understanding.
Target languages shipped with presets:

- 中文 (Mandarin)
- Bahasa Indonesia
- English
- 日本語
- 한국어
- Español
- Deutsch
- Français

Any language MiMo supports will work; the above are the presets the UI
exposes.

---

## Directory layout

```
omnidub/
├── apps/
│   ├── api/               FastAPI orchestrator
│   │   ├── main.py
│   │   ├── pipeline/      Per-stage modules
│   │   └── requirements.txt
│   └── web/               Mobile-first HTML UI
├── docs/                  Diagrams, screenshots
├── samples/               Example clips + expected output
├── docker-compose.yml
├── Dockerfile.api
├── .env.example
└── README.md
```

---

## License

MIT. Do what you want with it.

## Credits

- Xiaomi MiMo team — for the TTS model that finally treats emotion as a
  first-class input instead of a post-processing hack.
- ffmpeg — for being ffmpeg.
