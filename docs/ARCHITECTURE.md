# Architecture

OmniDub is a single-process FastAPI app that orchestrates the
Xiaomi MiMo-V2.5 family. There are no local ML models, no task queues,
and no third-party AI services in the hot path.

```
            ┌──────────────────────┐
   Browser ─┤  apps/web (static)   │
            └──────────┬───────────┘
                       │ multipart upload + SSE
                       ▼
   ┌───────────────────────────────────────────┐
   │   apps/api/main.py   FastAPI orchestrator │
   │                                           │
   │    POST /api/dub      → spawns DubJob     │
   │    GET  /api/stream/  ← SSE progress       │
   │    GET  /api/download ← final MP4          │
   └───────────────────┬───────────────────────┘
                       │
                       ▼
   ┌───────────────────────────────────────────┐
   │   pipeline/orchestrator.run_dub()         │
   │                                           │
   │   1  ffmpeg extract 16 kHz mono WAV       │
   │   2  MiMo-V2.5 audio-understanding →      │
   │      JSON { segments, speaker, start… }   │
   │   3  slice longest clip per speaker →     │
   │      base64 voice sample                  │
   │   4  per-segment frame strip →            │
   │      MiMo-V2.5 emotion classifier         │
   │   5  MiMo-V2.5-Pro timing-aware           │
   │      translator (retry ≤3×)               │
   │   6  MiMo-V2.5-TTS-VoiceClone render      │
   │      (concurrent, ×4)                     │
   │   7  numpy assemble dub track             │
   │   8  ffmpeg mux + duck original to −18 dB │
   └───────────────────────────────────────────┘
```

## Key design choices

### Why MiMo for everything
The cohesive story judges love is "one model family, one API key."
That means:
- ASR + diarization via MiMo audio understanding instead of Whisper.
- Emotion classification via MiMo vision instead of a CNN.
- Translation via MiMo-Pro reasoning instead of a specialized NMT model.
- TTS via MiMo-V2.5-TTS instead of ElevenLabs.

Removes the "is this project really about MiMo or is MiMo just a wrapper"
critique. Every arrow in the dataflow touches the MiMo API.

### Why emotion tags at the TTS level, not prosody post-processing
MiMo-V2.5-TTS accepts `(whispering)…text…` and `(angry)…text…`
inline in the assistant message. We push emotion into the TTS prompt
itself rather than trying to shape pitch/energy afterward. The model
handles it natively and the result is dramatically better than
post-hoc DSP.

### Why timing retries up to 3×
Dubbing fails for non-native viewers when a translated line overshoots
the original shot by ~15%+ — the dub talks over the next cut.
MiMo-V2.5-Pro is a reasoning model, so it can actually reason about
"your previous draft was 2.3s but the target is 1.8s, shorten by
dropping the filler 'you know'". Most NMT models cannot.

### Why voice cloning per speaker, not one voice
A typical auto-dub tool uses one voice for the whole video. If your
source has 3 speakers, the dub flattens them all into one narrator —
confusing the viewer. We slice the longest clean line of each speaker,
encode it as base64, and pass it as the `voice` handle for that
speaker's lines. Result: 3 distinct dubbed voices that match the
cadence and timbre of the originals.

## Scaling notes

The current single-process deployment handles ~1 concurrent dub job
per 2 vCPU / 4 GB RAM. Everything heavy (the model inference itself)
runs on MiMo's servers, so we are I/O bound, not CPU bound.

To scale:
- Swap the in-process `DubJob` dict for Redis + a worker pool.
- Upload sources to object storage (S3/R2) instead of local disk.
- Gate concurrent TTS calls per tenant if the MiMo account hits rate
  limits.

None of this is needed for demo/submission.
