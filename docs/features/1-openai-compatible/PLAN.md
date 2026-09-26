# OpenAI-Compatible TTS API — Implementation Plan

This is the engineering plan for the feature defined in `SPEC.md`. It intentionally does not implement the feature yet.

## Current Repository Context

The current server is implemented in `piper_sandbox/api.py` using `ThreadingHTTPServer` and `BaseHTTPRequestHandler`. It exposes native endpoints:

```text
GET  /health
GET  /models
POST /speak
POST /speak/chunks
GET  /
```

`POST /speak` already does the core work needed for OpenAI speech compatibility:

```text
JSON {text, model} -> PiperEngine.synthesize_bytes(...) -> audio/wav
```

The OpenAI-compatible implementation should therefore be a thin additive routing and validation layer around the existing engine. Avoid touching `PiperEngine` unless a small helper is clearly useful.

## Design Decisions

### Keep `/v1` separate from native routes

OpenAI clients expect `/v1/audio/speech` and OpenAI-style errors. Native clients currently expect `/speak`, `/speak/chunks`, plain-text errors in many cases, and the native `/models` shape. Mixing those contracts would create accidental regressions.

Implementation rule: all OpenAI-specific behavior lives behind paths beginning with `/v1/`.

### Support WAV only in V1

Piper returns WAV. Supporting OpenAI's `mp3`, `opus`, `aac` or `flac` would require transcoding and a runtime dependency such as ffmpeg. That conflicts with the current small stdlib design.

Implementation rule: `response_format` defaults to `wav`; any non-`wav` value returns a JSON `400` with code `unsupported_response_format`.

### Accept but ignore fields Piper cannot honor

OpenAI clients may send `speed` and `instructions`. Piper Sandbox currently does not expose stable speed/prosody control. Rejecting these fields makes compatibility worse; pretending to apply them is also misleading.

Implementation rule: validate `speed` range if present, accept `instructions` if present, and ignore both. Document this clearly.

### Add optional Bearer auth only for `/v1/*`

The project currently has no built-in auth. Turning auth on globally would break native clients and the bundled GUI.

Implementation rule: if `PIPER_OPENAI_API_KEY` is set, require `Authorization: Bearer <key>` for `/v1/*`; if unset, allow requests.

### Voice resolution is the main compatibility layer

OpenAI separates `model` and `voice`; Piper configured model names are actual voice model files. Use a resolver that can map OpenAI voice names to configured Piper models while still allowing direct Piper model names.

Implementation rule: centralize voice resolution in a small helper so `/v1/audio/speech`, `/v1/models` tests and future docs all use the same rules.

## Proposed Code Changes

### `piper_sandbox/api.py`

Add route branches:

```python
def do_GET(self):
    path = urlparse(self.path).path
    if path == "/v1/models":
        self._handle_openai_models()
        return
    if path.startswith("/v1/models/"):
        self._handle_openai_model(path)
        return
    ...existing routes...

def do_POST(self):
    parsed = urlparse(self.path)
    if parsed.path == "/v1/audio/speech":
        self._handle_openai_audio_speech()
        return
    ...existing routes...
```

Add handler methods:

```python
def _handle_openai_audio_speech(self) -> None: ...
def _handle_openai_models(self) -> None: ...
def _handle_openai_model(self, path: str) -> None: ...
```

Add helper methods:

```python
def _openai_enabled(self) -> bool: ...
def _require_openai_auth(self) -> bool: ...
def _send_openai_error(self, status, message, *, type, param=None, code=None): ...
def _send_openai_json(self, body, status=HTTPStatus.OK): ...
def _read_json_body(self): ...
def _openai_model_object(self, model_id, owned_by="piper-sandbox"): ...
```

Keep helper names private and local to `api.py` unless the file becomes too large. This feature can be implemented without a new module, but a small `openai_compat.py` module is acceptable if it reduces clutter.

### Optional `piper_sandbox/openai_compat.py`

Use this only if `api.py` becomes hard to follow. Candidate contents:

```python
OPENAI_TTS_MODEL_ALIASES = ("tts-1", "tts-1-hd", "gpt-4o-mini-tts")

def parse_voice_map(raw: str | None, default_model: str) -> dict[str, str]: ...
def resolve_openai_voice(voice: str | None, *, voice_map, default_voice, models) -> str: ...
def is_openai_tts_model(model: str, models) -> bool: ...
def openai_model_object(model_id: str, owned_by: str) -> dict: ...
```

Prefer this module if tests for parsing and resolution would otherwise require spinning up an HTTP server.

### `piper_sandbox/models.py`

No required changes. It already exposes `DEFAULT_MODEL` and `MODELS`.

Do not mutate `MODELS` for OpenAI aliases. OpenAI aliases are compatibility IDs, not actual Piper model specs.

### `.env.example`

Add:

```env
PIPER_OPENAI_COMPAT_ENABLED=true
PIPER_OPENAI_API_KEY=
PIPER_OPENAI_DEFAULT_MODEL=tts-1
PIPER_OPENAI_DEFAULT_VOICE=alloy
PIPER_OPENAI_VOICE_MAP={"alloy":"es_MX-ald-medium","echo":"es_MX-ald-medium","fable":"es_MX-ald-medium","onyx":"es_MX-ald-medium","nova":"es_MX-ald-medium","shimmer":"es_MX-ald-medium"}
```

If possible, in code default the map values to `DEFAULT_MODEL` rather than hard-coding `es_MX-ald-medium` in multiple places.

### `Dockerfile` and `docker-compose.yml`

Propagate new env vars if the existing Docker setup has an `ENV` block or environment passthrough list. Keep defaults aligned with `.env.example`.

### `README.md`

Add a concise OpenAI-compatible section:

- Explain `base_url=http://host:port/v1`.
- Show Python SDK example.
- Show JavaScript SDK example.
- State that V1 supports `response_format="wav"` only.
- Document optional `PIPER_OPENAI_API_KEY`.
- Document voice mapping.

### `docs/context/0-api/*`

Update cookbook only after core tests pass. Minimum changes:

- Add `/v1/audio/speech` to endpoint overview.
- Add a new recipe file only if useful, for example `07-openai-compatible.md`.
- Update operations doc to mention built-in optional Bearer auth for `/v1/*` if implemented.

## Handler Flow: `POST /v1/audio/speech`

1. Check OpenAI compatibility is enabled.
2. Check engine is enabled.
3. Check optional Bearer auth.
4. Read and cap request body using the same `MAX_REQUEST_BODY_BYTES` limit as `/speak`.
5. Parse JSON.
6. Validate `input` is non-empty string after trimming.
7. Validate `response_format` is absent or `wav`.
8. Validate `speed` if present: numeric and `0.25 <= speed <= 4.0`.
9. Validate `model`: absent defaults to `PIPER_OPENAI_DEFAULT_MODEL`; accepted values are OpenAI aliases or configured Piper model names.
10. Resolve `voice` to a configured Piper model.
11. Call `self.engine.synthesize_bytes(input_text, model=resolved_piper_model)`.
12. Return binary WAV with `Content-Type: audio/wav` and `Content-Length`.

Pseudo-code:

```python
def _handle_openai_audio_speech(self):
    if not self.openai_compat_enabled:
        self._send_openai_error(HTTPStatus.NOT_FOUND, "Not found", code="not_found")
        return
    if not self.engine_enabled:
        self._send_openai_error(HTTPStatus.NOT_FOUND, "Engine is disabled", code="not_found")
        return
    if not self._check_openai_auth():
        return

    try:
        payload = self._read_json_body()
        input_text = str(payload.get("input", "")).strip()
        if not input_text:
            raise OpenAIRequestError("Input cannot be empty", param="input", code="empty_input")

        response_format = str(payload.get("response_format", "wav")).lower()
        if response_format != "wav":
            raise OpenAIRequestError("Only response_format='wav' is supported", param="response_format", code="unsupported_response_format")

        model = str(payload.get("model", self.openai_default_model))
        validate_openai_model(model)

        voice = payload.get("voice")
        piper_model = resolve_voice(voice, model=model)
        wav = self.engine.synthesize_bytes(input_text, model=piper_model)
    except OpenAIRequestError as exc:
        self._send_openai_error(HTTPStatus.BAD_REQUEST, exc.message, param=exc.param, code=exc.code)
        return
    except PiperError as exc:
        self._send_openai_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc), type="server_error", code="piper_error")
        return

    self.send_response(HTTPStatus.OK)
    self.send_header("Content-Type", "audio/wav")
    self.send_header("Content-Length", str(len(wav)))
    self.send_header("X-Piper-Model", piper_model)
    self.send_header("X-OpenAI-Compatible", "true")
    self._send_cors_headers()
    self.end_headers()
    self.wfile.write(wav)
```

## Handler Flow: `GET /v1/models`

1. Check compatibility enabled.
2. Check optional Bearer auth.
3. Return OpenAI aliases and configured Piper models as model objects.

No synthesis or model download should happen here.

## Handler Flow: `GET /v1/models/{model}`

1. URL-decode the model id segment.
2. Check whether it is an accepted OpenAI alias or configured Piper model.
3. Return one model object or `404` OpenAI-style JSON.

## Error Handling Plan

Create a single OpenAI error sender. Do not reuse `_send_error` because native routes return plain text.

```python
def _send_openai_error(
    self,
    status: HTTPStatus,
    message: str,
    *,
    error_type: str = "invalid_request_error",
    param: str | None = None,
    code: str | None = None,
) -> None:
    self._send_json({"error": {"message": message, "type": error_type, "param": param, "code": code}}, status)
```

Be careful: `_send_json` currently uses UTF-8 JSON and CORS, which is fine for OpenAI JSON errors. For auth failures, include `WWW-Authenticate: Bearer` if practical; if `_send_json` cannot add custom headers, either add an optional headers argument or send manually.

## Auth Plan

At startup in `main()`:

```python
PiperRequestHandler.openai_compat_enabled = env_bool("PIPER_OPENAI_COMPAT_ENABLED", True)
PiperRequestHandler.openai_api_key = os.environ.get("PIPER_OPENAI_API_KEY", "")
PiperRequestHandler.openai_default_model = os.environ.get("PIPER_OPENAI_DEFAULT_MODEL", "tts-1")
PiperRequestHandler.openai_default_voice = os.environ.get("PIPER_OPENAI_DEFAULT_VOICE", "alloy")
PiperRequestHandler.openai_voice_map = parse_voice_map(os.environ.get("PIPER_OPENAI_VOICE_MAP"), DEFAULT_MODEL)
```

Request check:

```python
def _check_openai_auth(self) -> bool:
    if not self.openai_api_key:
        return True
    expected = f"Bearer {self.openai_api_key}"
    if self.headers.get("Authorization") == expected:
        return True
    self._send_openai_error(HTTPStatus.UNAUTHORIZED, "Invalid API key", error_type="authentication_error", code="invalid_api_key")
    return False
```

Do not log the configured key or incoming token.

## Test Plan

Add `tests/test_openai_compat.py`.

Use the same pattern as `tests/test_speak_chunks_endpoint.py`:

- Monkeypatch `PiperRequestHandler.engine` to a fake engine returning a small silent WAV.
- Start `ThreadingHTTPServer` on an ephemeral port.
- Reset handler class attributes per fixture so tests do not leak state.

Core tests:

- `POST /v1/audio/speech` returns `200`, `audio/wav`, and a `RIFF` body.
- Request with OpenAI alias `model="tts-1"` and `voice="alloy"` resolves to `DEFAULT_MODEL`.
- Request with direct Piper model as `voice` resolves directly.
- Request with direct Piper model as `model` and no `voice` resolves to that model.
- Missing `response_format` defaults to WAV.
- `response_format="mp3"` returns `400` JSON with code `unsupported_response_format`.
- Empty `input` returns `400` JSON with param `input`.
- Invalid JSON returns `400` JSON.
- Unknown `voice` returns `400` JSON with code `voice_not_found`.
- Unknown `model` returns `400` JSON with code `model_not_supported`.
- Payload larger than `MAX_REQUEST_BODY_BYTES` returns `413` JSON.
- Fake `PiperError` returns `500` JSON with code `piper_error`.
- `PIPER_SERVICE_MODE=gui` equivalent returns `404` for `/v1/audio/speech`.
- Compat disabled returns `404` for `/v1/audio/speech` and `/v1/models`.
- When `openai_api_key` is set, missing or wrong Authorization returns `401`.
- When `openai_api_key` is set, correct `Authorization: Bearer ...` succeeds.
- When auth is not set, any or no Authorization header succeeds.
- `OPTIONS /v1/audio/speech` includes `Authorization` in `Access-Control-Allow-Headers`.
- `GET /v1/models` returns object list with `tts-1` and configured Piper model names.
- `GET /v1/models/tts-1` returns one model object.
- `GET /v1/models/not-real` returns `404` JSON.

Optional integration checks after unit tests:

- `python -m compileall piper_sandbox`
- `pytest`
- Manual OpenAI Python SDK call if dependency is available in the active environment. Do not add OpenAI SDK as a project dependency only for this check.

## Documentation Plan

Update after code and tests pass:

1. README configuration section.
2. README endpoint section.
3. API cookbook overview.
4. Optional new cookbook recipe for OpenAI SDK clients.
5. Operations doc auth section, clearly distinguishing `/v1/*` built-in token from proxy auth for the native API.

## Migration and Compatibility Notes

- Native clients continue using `/speak` and `/speak/chunks` unchanged.
- Existing GUI behavior is unchanged.
- OpenAI clients should set `response_format="wav"` explicitly even though the server defaults to WAV.
- If a deployment already uses a reverse proxy for auth, `PIPER_OPENAI_API_KEY` can remain empty and the proxy can continue enforcing auth.
- If both proxy auth and `PIPER_OPENAI_API_KEY` are used, clients must satisfy both layers.

## Risks and Mitigations

### SDK default response format

OpenAI defaults speech output to MP3. This server cannot produce MP3 in V1. Some client code may omit `response_format` and name the output `.mp3`.

Mitigation: server defaults to WAV and docs show explicit `response_format="wav"`. Unsupported explicit formats fail loudly.

### Type-restricted SDK voice values

Some SDK versions type `voice` as a limited set of OpenAI names. Direct Piper model names may be inconvenient in typed code.

Mitigation: map standard OpenAI voice names to Piper models via `PIPER_OPENAI_VOICE_MAP`.

### Security expectations

OpenAI APIs always require API keys, but this project currently defaults to no built-in auth.

Mitigation: support optional `PIPER_OPENAI_API_KEY` and document reverse-proxy auth for production.

### Misleading model list

OpenAI aliases such as `tts-1-hd` do not actually change Piper quality unless mapped to different voices.

Mitigation: treat aliases as compatibility selectors only; document that `voice`/mapping controls the actual Piper model.

## Out of Scope for V1

- MP3/AAC/Opus/FLAC output.
- True OpenAI-compatible streaming endpoint.
- OpenAI-compatible `/v1/chat/completions` or `/v1/responses`.
- Per-request language selection beyond choosing a Piper model.
- Applying `speed` or `instructions` to Piper synthesis.
- Admin endpoints for changing voice maps at runtime.
