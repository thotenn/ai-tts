# OpenAI-Compatible TTS API

## Summary

Add an OpenAI-compatible HTTP surface for text-to-speech clients without replacing the current Piper Sandbox API. The current endpoints remain stable:

```text
GET  /health
GET  /models
POST /speak
POST /speak/chunks
GET  /
```

This feature adds OpenAI-style versioned endpoints under `/v1`, with the primary target being `POST /v1/audio/speech` so existing OpenAI SDK clients can point their `base_url` at Piper Sandbox and request local TTS.

## Compatibility Target

V1 targets OpenAI's audio speech contract, not the entire OpenAI API.

Supported in V1:

- `POST /v1/audio/speech`
- `GET /v1/models`
- `GET /v1/models/{model}`
- OpenAI-style JSON error bodies for `/v1/*` routes
- Optional `Authorization: Bearer ...` checking via env
- CORS preflight that allows `Authorization`

Not supported in V1:

- Chat completions, responses, embeddings, images, transcription, translation, realtime, assistants, files, batches or fine-tuning.
- OpenAI audio output formats other than `wav`.
- Exact OpenAI model behavior, prosody instructions, or cloud TTS voice identity.
- Streaming SSE for `/v1/audio/speech`. OpenAI's speech endpoint returns one binary audio response, and this project already has `/speak/chunks` as a non-OpenAI extension.

## Goals

- Let OpenAI SDK users call local Piper TTS with minimal client changes.
- Keep the implementation stdlib-only; no FastAPI, Flask, ffmpeg or new runtime server dependency.
- Preserve all existing endpoints and response shapes.
- Keep `engine`/`gui`/`both` service-mode gating correct.
- Make unsupported OpenAI features fail clearly instead of silently pretending to work.
- Provide a small voice-mapping layer so common OpenAI voice names work out of the box.

## Non-Goals

- No full OpenAI API clone.
- No MP3/AAC/Opus/FLAC transcoding in V1.
- No auth system beyond one optional static Bearer token.
- No per-user quotas, billing, rate limiting or persistence.
- No changes to `PiperEngine` synthesis quality or model download behavior unless needed for the wrapper.
- No breaking changes to `/models`; OpenAI-compatible model listing is served separately from `/v1/models`.

## Endpoint: `POST /v1/audio/speech`

### Availability

Available only when the engine is enabled:

- `PIPER_SERVICE_MODE=both`: available.
- `PIPER_SERVICE_MODE=engine`: available.
- `PIPER_SERVICE_MODE=gui`: returns `404` because the local process has no engine.

If `PIPER_OPENAI_COMPAT_ENABLED=false`, all `/v1/*` compatibility routes return `404`.

### Request

```http
POST /v1/audio/speech
Content-Type: application/json
Authorization: Bearer optional-token
```

Body:

```json
{
  "model": "tts-1",
  "input": "Hola desde Piper con una API compatible con OpenAI.",
  "voice": "alloy",
  "response_format": "wav",
  "speed": 1.0,
  "instructions": "Speak warmly."
}
```

### Request fields

| Field | Type | Required | V1 behavior |
| --- | --- | --- | --- |
| `input` | string | yes | Text to synthesize. Maps to current `/speak` `text`. Empty or whitespace-only input returns `400`. |
| `model` | string | no | Accepted for OpenAI client compatibility. Known OpenAI aliases are accepted. Piper model names are also accepted. Unknown values return `400`. Defaults to `tts-1`. |
| `voice` | string | no | Selects the Piper voice via mapping. Defaults to `alloy`, which maps to `PIPER_DEFAULT_MODEL`. A configured Piper model name is also accepted directly. |
| `response_format` | string | no | V1 supports only `wav`. Missing value defaults to `wav` for local compatibility. Any other value returns `400`. |
| `speed` | number | no | Accepted and validated as OpenAI-compatible range `0.25 <= speed <= 4.0`, but ignored in V1 because the current `PiperEngine` does not expose speed control. |
| `instructions` | string | no | Accepted and ignored in V1. Piper voices cannot follow natural-language style instructions. |

Unknown extra fields are ignored, matching the pragmatic behavior needed by SDK wrappers that may add optional fields over time.

### Model field semantics

OpenAI uses `model` to select the TTS model family and `voice` to select the voice. Piper's configured model name is effectively both model file and voice.

V1 accepts these `model` values:

- `tts-1`
- `tts-1-hd`
- `gpt-4o-mini-tts`
- Any configured Piper model name from `MODELS`

For OpenAI aliases, the actual Piper model is selected by `voice`. For a Piper model name passed as `model`, `voice` still wins if provided; otherwise the `model` value itself is used as the Piper model.

Examples:

```json
{"model":"tts-1","voice":"alloy","input":"Hola","response_format":"wav"}
```

Uses `PIPER_OPENAI_VOICE_MAP["alloy"]` or `PIPER_DEFAULT_MODEL`.

```json
{"model":"es_MX-ald-medium","input":"Hola","response_format":"wav"}
```

Uses `es_MX-ald-medium` directly.

```json
{"model":"tts-1","voice":"es_ES-carlfm-x_low","input":"Hola","response_format":"wav"}
```

Uses `es_ES-carlfm-x_low` directly if it is configured.

### Voice mapping

Add a voice resolver with this precedence:

1. If `voice` exactly matches a configured Piper model name, use it.
2. Else if `voice` exists in `PIPER_OPENAI_VOICE_MAP`, use the mapped Piper model.
3. Else if `voice` is missing, use `PIPER_OPENAI_DEFAULT_VOICE` and resolve it by the same rules.
4. Else return `400` with an OpenAI-style error.

Default config:

```env
PIPER_OPENAI_DEFAULT_VOICE=alloy
PIPER_OPENAI_VOICE_MAP={"alloy":"es_MX-ald-medium","echo":"es_MX-ald-medium","fable":"es_MX-ald-medium","onyx":"es_MX-ald-medium","nova":"es_MX-ald-medium","shimmer":"es_MX-ald-medium"}
```

At runtime, mapped values must exist in `MODELS`; invalid mappings should fail at startup or on first use with a clear error. Prefer startup validation so deployment mistakes are visible early.

Optional newer OpenAI voice names may also be accepted if present in the env map, for example `ash`, `ballad`, `coral`, `sage` and `verse`.

### Successful response

```http
HTTP/1.1 200 OK
Content-Type: audio/wav
Content-Length: <bytes>
```

Response body is the complete WAV returned by `PiperEngine.synthesize_bytes`.

Headers:

- `Content-Type: audio/wav`
- `Content-Length: <len>`
- Existing CORS headers
- Optional: `X-Piper-Model: <resolved-piper-model>` for debugging
- Optional: `X-OpenAI-Compatible: true` for debugging

Do not base64-encode audio for this endpoint. OpenAI's speech endpoint returns binary audio.

### Error responses

All `/v1/*` errors should return JSON with an OpenAI-like shape:

```json
{
  "error": {
    "message": "Input cannot be empty",
    "type": "invalid_request_error",
    "param": "input",
    "code": "empty_input"
  }
}
```

Common statuses:

| Status | Condition | Error type | Code |
| --- | --- | --- | --- |
| `400` | Invalid JSON | `invalid_request_error` | `invalid_json` |
| `400` | Empty `input` | `invalid_request_error` | `empty_input` |
| `400` | Unsupported `response_format` | `invalid_request_error` | `unsupported_response_format` |
| `400` | Unsupported `model` | `invalid_request_error` | `model_not_supported` |
| `400` | Unknown `voice` or mapped Piper model | `invalid_request_error` | `voice_not_found` |
| `401` | Missing/invalid Bearer token when auth is configured | `authentication_error` | `invalid_api_key` |
| `404` | OpenAI compat disabled, route absent, or engine disabled | `invalid_request_error` | `not_found` |
| `413` | Request body over `MAX_REQUEST_BODY_BYTES` | `invalid_request_error` | `payload_too_large` |
| `500` | Piper synthesis failure that is not a user validation problem | `server_error` | `piper_error` |

For existing non-`/v1` routes, keep current plain-text errors unless separately changed by another feature.

## Endpoint: `GET /v1/models`

### Purpose

Return an OpenAI-style model list so SDKs, probes and dashboards can discover that this server has TTS-compatible models.

### Response

```json
{
  "object": "list",
  "data": [
    {
      "id": "tts-1",
      "object": "model",
      "created": 0,
      "owned_by": "piper-sandbox"
    },
    {
      "id": "tts-1-hd",
      "object": "model",
      "created": 0,
      "owned_by": "piper-sandbox"
    },
    {
      "id": "gpt-4o-mini-tts",
      "object": "model",
      "created": 0,
      "owned_by": "piper-sandbox"
    },
    {
      "id": "es_MX-ald-medium",
      "object": "model",
      "created": 0,
      "owned_by": "piper"
    }
  ]
}
```

The list should include:

- OpenAI TTS aliases accepted by `/v1/audio/speech`.
- Configured Piper model names from `MODELS`.

Do not change `GET /models`; it remains the Piper-native model registry response.

## Endpoint: `GET /v1/models/{model}`

Return one model object when `{model}` is accepted by `/v1/audio/speech`; otherwise return `404` with OpenAI-style JSON error.

Example:

```json
{
  "id": "tts-1",
  "object": "model",
  "created": 0,
  "owned_by": "piper-sandbox"
}
```

## Authentication

The project currently has no built-in auth. Preserve that default.

Add optional static Bearer auth for `/v1/*` routes:

```env
PIPER_OPENAI_API_KEY=
```

Behavior:

- If `PIPER_OPENAI_API_KEY` is empty or unset, requests are accepted regardless of `Authorization` header.
- If set, `/v1/*` requests must send `Authorization: Bearer <value>`.
- Invalid or missing token returns `401` with OpenAI-style JSON.
- This auth applies only to `/v1/*` in V1. Existing routes remain unchanged to avoid breaking deployments. A future feature can generalize auth.

This lets OpenAI SDKs pass any local dummy key during development when auth is off:

```python
OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="local")
```

## CORS

Current CORS allows `Content-Type` only in `Access-Control-Allow-Headers`. OpenAI-compatible browser calls commonly include `Authorization`, so preflight must allow it.

Update `do_OPTIONS` response:

```text
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization
```

Keep `PIPER_CORS_ORIGIN` behavior unchanged.

## Configuration

Add these variables to `.env.example`, README and Docker env where applicable:

```env
PIPER_OPENAI_COMPAT_ENABLED=true
PIPER_OPENAI_API_KEY=
PIPER_OPENAI_DEFAULT_MODEL=tts-1
PIPER_OPENAI_DEFAULT_VOICE=alloy
PIPER_OPENAI_VOICE_MAP={"alloy":"es_MX-ald-medium","echo":"es_MX-ald-medium","fable":"es_MX-ald-medium","onyx":"es_MX-ald-medium","nova":"es_MX-ald-medium","shimmer":"es_MX-ald-medium"}
```

Notes:

- `PIPER_OPENAI_DEFAULT_MODEL` must be one of the accepted OpenAI aliases or a configured Piper model name.
- `PIPER_OPENAI_DEFAULT_VOICE` must resolve through direct Piper model match or voice map.
- `PIPER_OPENAI_VOICE_MAP` is a JSON object of `openai_voice_name -> piper_model_name`.
- Defaults should be generated from `DEFAULT_MODEL` in code where practical, not duplicated in a way that can drift.

## Suggested Client Usage

### Python OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="local")

with client.audio.speech.with_streaming_response.create(
    model="tts-1",
    voice="alloy",
    input="Hola desde Piper.",
    response_format="wav",
) as response:
    response.stream_to_file("salida.wav")
```

### JavaScript OpenAI SDK

```js
import OpenAI from 'openai';
import { writeFile } from 'node:fs/promises';

const openai = new OpenAI({
  baseURL: 'http://127.0.0.1:8000/v1',
  apiKey: 'local',
});

const response = await openai.audio.speech.create({
  model: 'tts-1',
  voice: 'alloy',
  input: 'Hola desde Piper.',
  response_format: 'wav',
});

await writeFile('salida.wav', Buffer.from(await response.arrayBuffer()));
```

## Interaction With `/speak/chunks`

`/v1/audio/speech` returns one complete audio file, matching OpenAI speech behavior. It should not switch to NDJSON when `PIPER_CHUNKS_ENABLED=true`.

Existing `/speak/chunks` remains the progressive local extension. Future work can add an explicitly non-OpenAI endpoint under `/v1/audio/speech/chunks` only if a client need appears, but V1 should not add it.

## Implementation Constraints

- Keep using `BaseHTTPRequestHandler` and helper methods in `api.py`.
- Keep body limit at `MAX_REQUEST_BODY_BYTES`.
- Do not import OpenAI SDK server-side.
- Do not add a web framework.
- Do not add audio transcoding dependencies.
- Keep response generation synchronous, matching current `/speak`.
- Ensure all OpenAI-compatible routing is additive and scoped to `/v1/*`.

## Acceptance Criteria

- Existing tests pass without changing existing endpoint contracts.
- `POST /v1/audio/speech` with `response_format="wav"` returns a valid `audio/wav` body beginning with `RIFF`.
- OpenAI Python SDK can save a WAV when configured with `base_url="http://127.0.0.1:8000/v1"` and a dummy key while auth is disabled.
- `GET /v1/models` returns OpenAI-style model objects.
- Optional Bearer auth works when `PIPER_OPENAI_API_KEY` is configured.
- GUI-only mode does not expose local engine synthesis through `/v1/audio/speech`.
- Unsupported formats such as `mp3` fail with JSON `unsupported_response_format`, not a misleading WAV response.
