# 01 — Quickstart

Minimal walkthrough with `curl`. Replace `https://tts.example.com` with your engine URL.

## 1. Verify the engine is reachable

```bash
curl https://tts.example.com/health
```

```json
{"status":"ok","mode":"both","engine":true,"gui":true,"chunks_enabled":true}
```

If `chunks_enabled` is `false`, only `/speak` is available; `/speak/chunks` will return `501`.

## 2. List available voices

```bash
curl https://tts.example.com/models
```

```json
{
  "default": "es_MX-ald-medium",
  "models": [
    {"name": "es_MX-claude-high",  "language": "es", "country": "MX", "quality": "high",  ...},
    {"name": "es_MX-ald-medium",   "language": "es", "country": "MX", "quality": "medium",...},
    {"name": "es_ES-carlfm-x_low", "language": "es", "country": "ES", "quality": "x_low", ...}
  ]
}
```

Each model name follows the pattern `language_COUNTRY-voice-quality`.

## 3. Synthesize a short phrase

```bash
curl -X POST https://tts.example.com/speak \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hola, esto es una prueba.","model":"es_MX-ald-medium"}' \
  --output prueba.wav

file prueba.wav
# prueba.wav: RIFF (little-endian) data, WAVE audio, ...
```

Play with whatever you have:

```bash
paplay prueba.wav   # PulseAudio
aplay prueba.wav    # ALSA
ffplay prueba.wav   # ffmpeg
```

## 4. Stream a long passage

```bash
curl -N -X POST https://tts.example.com/speak/chunks \
  -H 'Content-Type: application/json' \
  -d '{"text":"Un parrafo largo de prueba que se va a dividir en varios chunks...","model":"es_MX-ald-medium"}'
```

`-N` (`--no-buffer`) is important — without it `curl` may hold all output until the stream ends, defeating the demo.

You'll see one JSON object per line:

```text
{"type":"meta","model":"es_MX-ald-medium","chunks":3,"target_chars":350,...}
{"type":"chunk","index":0,"chars":318,"split_reason":"sentence","synthesis_seconds":1.42,"duration_seconds":8.21,"rtf":0.17,"audio_base64":"UklGRg..."}
{"type":"chunk","index":1, ...}
{"type":"chunk","index":2, ...}
{"type":"done"}
```

To extract and play the first chunk:

```bash
curl -sN -X POST https://tts.example.com/speak/chunks \
  -H 'Content-Type: application/json' \
  -d '{"text":"Texto largo...","model":"es_MX-ald-medium"}' \
| jq -r 'select(.type=="chunk" and .index==0).audio_base64' \
| head -1 | base64 -d > chunk0.wav
```

## Common pitfalls

- **Missing `Content-Type: application/json`** → server can't parse the body and returns `400`.
- **Empty `text`** → `400` with `text cannot be empty`.
- **Unknown `model`** → `400` listing the available models.
- **Reverse proxy buffering** the chunked response → you see everything arrive at once instead of progressively. Check that the proxy is not buffering this route.

Next: language-specific recipes in [02-python.md](02-python.md) and [03-javascript.md](03-javascript.md).
