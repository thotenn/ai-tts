# Piper Sandbox API Cookbook

Practical recipes for consuming the Piper Sandbox HTTP API from your own applications. Each recipe is self-contained — copy, paste, adapt.

Assumes you have an engine running somewhere reachable. Examples use `https://tts.example.com` as the engine URL; replace with yours.

## Contents

| Recipe | What it covers |
| --- | --- |
| [01-quickstart.md](01-quickstart.md) | Hello world with curl. Endpoints at a glance. Model selection. |
| [02-python.md](02-python.md) | Python client patterns. Sync (`urllib`/`requests`) and chunked streaming. A reusable `PiperClient` class. |
| [03-javascript.md](03-javascript.md) | Browser fetch and Node.js. NDJSON streaming with `getReader()`. Playback queue. |
| [04-streaming.md](04-streaming.md) | Deep dive on `/speak/chunks`: event shape, when to use chunks vs full WAV, cancellation, backpressure. |
| [05-chat-with-voice.md](05-chat-with-voice.md) | LLM → TTS integration patterns. From simple "speak the answer" to sentence-by-sentence streaming for a conversational feel. |
| [06-operations.md](06-operations.md) | CORS, auth, rate limiting, custom models, health checks, deployment notes. |

## API surface at a glance

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/health` | GET | Liveness probe; reports mode and `chunks_enabled` |
| `/models` | GET | List configured voices with metadata |
| `/speak` | POST | Synthesize text → one WAV (returns `audio/wav`) |
| `/speak/chunks` | POST | Synthesize text → NDJSON stream of chunked WAVs (lower time-to-first-audio for long text) |
| `/` | GET | Reference web GUI (only in `both` and `gui` modes) |

Request body for both speak endpoints:

```json
{"text": "Hola mundo", "model": "es_MX-ald-medium"}
```

`model` is optional and defaults to whatever `PIPER_DEFAULT_MODEL` is set to on the server.

## Choosing the right endpoint

- **`/speak`** — short text (< ~300 chars), pre-generated audio for caching, anything where you'll wait for the whole file before doing anything with it. Returns one WAV blob.
- **`/speak/chunks`** — long text, interactive UX, anything where time-to-first-audio matters. Returns NDJSON with one chunked WAV per line. Requires `PIPER_CHUNKS_ENABLED=true` on the server.

When in doubt: short → `/speak`, long or interactive → `/speak/chunks`.
