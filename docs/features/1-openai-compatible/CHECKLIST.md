# OpenAI-Compatible TTS API — Checklist

This checklist is organized by implementation phases. Keep each item small enough to verify independently.

## Phase 1 — Compatibility Contract and Helpers

- [ ] Confirm `SPEC.md` scope: TTS only, no full OpenAI API clone.
- [ ] Decide whether helpers stay in `api.py` or move to `piper_sandbox/openai_compat.py`.
- [ ] Add OpenAI TTS model aliases: `tts-1`, `tts-1-hd`, `gpt-4o-mini-tts`.
- [ ] Add parser for `PIPER_OPENAI_VOICE_MAP` JSON object.
- [ ] Add default voice map that maps standard OpenAI voices to `DEFAULT_MODEL`.
- [ ] Add validation that mapped Piper models exist in `MODELS`.
- [ ] Add resolver for `voice` with precedence: direct Piper model, mapped OpenAI voice, default voice.
- [ ] Add validator for `model`: OpenAI alias or configured Piper model.
- [ ] Add OpenAI model-object builder with `id`, `object`, `created`, `owned_by`.
- [ ] Add OpenAI-style JSON error helper.

## Phase 2 — Configuration

- [ ] Add handler class attributes for OpenAI compat defaults.
- [ ] Read `PIPER_OPENAI_COMPAT_ENABLED` at startup, default `true`.
- [ ] Read `PIPER_OPENAI_API_KEY` at startup, default empty.
- [ ] Read `PIPER_OPENAI_DEFAULT_MODEL` at startup, default `tts-1`.
- [ ] Read `PIPER_OPENAI_DEFAULT_VOICE` at startup, default `alloy`.
- [ ] Read and parse `PIPER_OPENAI_VOICE_MAP` at startup.
- [ ] Fail startup or produce a clear configuration error for invalid JSON voice map.
- [ ] Fail startup or produce a clear configuration error when default voice cannot resolve.
- [ ] Add new variables to `.env.example`.
- [ ] Add new variables to Docker `ENV` or Compose passthrough where applicable.

## Phase 3 — Routing and Auth

- [ ] Route `POST /v1/audio/speech` before native `/speak` handling.
- [ ] Route `GET /v1/models` before native `/models` handling.
- [ ] Route `GET /v1/models/{model}`.
- [ ] Return `404` JSON for `/v1/*` when `PIPER_OPENAI_COMPAT_ENABLED=false`.
- [ ] Return `404` JSON for `/v1/audio/speech` when service mode is `gui`.
- [ ] Add optional Bearer auth check for `/v1/*` only.
- [ ] Return `401` JSON for missing token when `PIPER_OPENAI_API_KEY` is set.
- [ ] Return `401` JSON for wrong token when `PIPER_OPENAI_API_KEY` is set.
- [ ] Allow requests with no auth when `PIPER_OPENAI_API_KEY` is empty.
- [ ] Do not apply OpenAI auth to native `/speak`, `/speak/chunks`, `/models`, `/health`, or `/`.
- [ ] Update `do_OPTIONS` to allow `Authorization` in `Access-Control-Allow-Headers`.

## Phase 4 — `POST /v1/audio/speech`

- [ ] Reuse `MAX_REQUEST_BODY_BYTES` body limit.
- [ ] Parse request JSON and return OpenAI-style `400` on invalid JSON.
- [ ] Read `input` field and reject empty/whitespace-only input.
- [ ] Default missing `model` to `PIPER_OPENAI_DEFAULT_MODEL`.
- [ ] Validate `model` as OpenAI alias or configured Piper model.
- [ ] Default missing `voice` to `PIPER_OPENAI_DEFAULT_VOICE`.
- [ ] Resolve `voice` to a configured Piper model.
- [ ] Default missing `response_format` to `wav`.
- [ ] Accept `response_format="wav"` case-insensitively.
- [ ] Reject explicit non-WAV formats with `unsupported_response_format`.
- [ ] Validate `speed` if present as number in `0.25..4.0`.
- [ ] Accept and ignore `instructions`.
- [ ] Ignore unknown extra fields.
- [ ] Call `PiperEngine.synthesize_bytes(input, model=resolved_piper_model)`.
- [ ] Return `200 audio/wav` with `Content-Length` and WAV bytes.
- [ ] Add optional debug headers `X-Piper-Model` and `X-OpenAI-Compatible`.
- [ ] Return `500` OpenAI-style JSON on unexpected `PiperError`.
- [ ] Ensure native `/speak` remains byte-compatible.

## Phase 5 — `GET /v1/models`

- [ ] Return `{"object":"list","data":[...]}` shape.
- [ ] Include OpenAI aliases accepted by `POST /v1/audio/speech`.
- [ ] Include configured Piper model names from `MODELS`.
- [ ] Mark OpenAI aliases as `owned_by="piper-sandbox"`.
- [ ] Mark direct Piper models as `owned_by="piper"`.
- [ ] Do not trigger model downloads from this endpoint.
- [ ] Keep native `GET /models` response unchanged.

## Phase 6 — `GET /v1/models/{model}`

- [ ] URL-decode model id path segment.
- [ ] Return one OpenAI-style model object for accepted OpenAI aliases.
- [ ] Return one OpenAI-style model object for configured Piper model names.
- [ ] Return `404` OpenAI-style JSON for unknown model id.
- [ ] Apply optional Bearer auth consistently.

## Phase 7 — Tests

- [ ] Add `tests/test_openai_compat.py`.
- [ ] Add fake engine fixture returning a small valid silent WAV.
- [ ] Add threaded HTTP server fixture with isolated handler class attributes.
- [ ] Test successful `POST /v1/audio/speech` returns `audio/wav` and `RIFF` bytes.
- [ ] Test OpenAI alias `model="tts-1"` plus `voice="alloy"` resolves to default Piper model.
- [ ] Test direct Piper model in `voice` resolves directly.
- [ ] Test direct Piper model in `model` works when `voice` is omitted.
- [ ] Test missing `response_format` defaults to WAV.
- [ ] Test `response_format="mp3"` returns `400` with code `unsupported_response_format`.
- [ ] Test empty `input` returns `400` with param `input`.
- [ ] Test invalid JSON returns `400` JSON.
- [ ] Test unknown `voice` returns `400` with code `voice_not_found`.
- [ ] Test unknown `model` returns `400` with code `model_not_supported`.
- [ ] Test oversized payload returns `413` JSON.
- [ ] Test fake `PiperError` returns `500` with code `piper_error`.
- [ ] Test GUI mode returns `404` for `/v1/audio/speech`.
- [ ] Test compat disabled returns `404` for `/v1/audio/speech`.
- [ ] Test compat disabled returns `404` for `/v1/models`.
- [ ] Test auth disabled allows missing Authorization.
- [ ] Test auth enabled rejects missing Authorization with `401`.
- [ ] Test auth enabled rejects wrong Bearer token with `401`.
- [ ] Test auth enabled accepts correct Bearer token.
- [ ] Test `OPTIONS /v1/audio/speech` allows `Authorization` header.
- [ ] Test `GET /v1/models` returns `object="list"` and expected IDs.
- [ ] Test `GET /v1/models/tts-1` returns one model object.
- [ ] Test `GET /v1/models/not-real` returns `404` JSON.
- [ ] Test native `/speak` still returns `audio/wav`.
- [ ] Test native `/models` shape remains unchanged.

## Phase 8 — Documentation

- [ ] Update README configuration table/env block.
- [ ] Update README endpoint list with `/v1/audio/speech` and `/v1/models`.
- [ ] Add Python OpenAI SDK example with `response_format="wav"`.
- [ ] Add JavaScript OpenAI SDK example with `response_format: "wav"`.
- [ ] Document WAV-only V1 limitation.
- [ ] Document `PIPER_OPENAI_API_KEY` optional Bearer auth.
- [ ] Document `PIPER_OPENAI_VOICE_MAP` examples.
- [ ] Update `docs/context/0-api/README.md` endpoint overview.
- [ ] Add optional cookbook page for OpenAI-compatible clients.
- [ ] Update operations doc to distinguish `/v1/*` static Bearer auth from proxy auth for native routes.

## Phase 9 — Validation

- [ ] Run `python -m compileall piper_sandbox`.
- [ ] Run `pytest`.
- [ ] Manually call `/v1/audio/speech` with curl and save `salida.wav`.
- [ ] Verify saved file begins with `RIFF`.
- [ ] Manually call `/v1/models` and inspect OpenAI-style shape.
- [ ] Manually verify service mode `engine`: `/v1/audio/speech` works and `/` remains disabled.
- [ ] Manually verify service mode `gui`: `/v1/audio/speech` returns `404` and GUI still loads.
- [ ] If OpenAI Python SDK is available, verify a local `OpenAI(base_url="...")` speech request saves WAV.
- [ ] If OpenAI JavaScript SDK is available, verify a local `audio.speech.create` request saves WAV.
- [ ] Verify Docker Compose config still parses.

## Final Acceptance

- [ ] Existing native API behavior is unchanged.
- [ ] OpenAI-compatible TTS works through `/v1/audio/speech` for WAV output.
- [ ] OpenAI-compatible model discovery works through `/v1/models`.
- [ ] Optional Bearer auth works for `/v1/*` without affecting native routes.
- [ ] Unsupported formats and routes fail clearly with JSON errors.
- [ ] Tests and docs cover the compatibility boundary and known limitations.
