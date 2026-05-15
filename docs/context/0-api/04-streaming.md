# 04 — Streaming Deep Dive

Everything you need to know about `/speak/chunks` beyond the quickstart.

## Why streaming at all

`/speak` synthesizes the whole input before returning. For 30 seconds of audio that's typically 5-10 seconds of wall time on a modern CPU. The user stares at a spinner the whole time.

`/speak/chunks` splits the input, synthesizes each chunk and emits it the moment it's ready. The client can start playback after chunk 0 (typically 1-2 seconds for a 600-char paragraph) while the rest are still being synthesized. Total wall time is the same, but **time-to-first-audio** drops dramatically.

Rule of thumb: under ~300 characters, the chunking overhead is not worth it — use `/speak`. Above that, prefer `/speak/chunks`.

## Event stream contract

The response is `Content-Type: application/x-ndjson; charset=utf-8`, no `Content-Length`, terminated by connection close. Each line is one JSON object terminated by `\n`.

Sequence on success:

```text
meta → chunk → chunk → ... → done
```

Sequence on mid-stream Piper failure:

```text
meta → chunk → ... → error
```

There is **no** `done` after an `error`. Treat both as terminal.

### `meta` (first line)

```json
{
  "type": "meta",
  "model": "es_MX-ald-medium",
  "chunks": 4,
  "target_chars": 350,
  "min_chars": 120,
  "max_chars": 700
}
```

`chunks` is the planned count — the server splits the entire input before synthesizing anything, so this is known up front. You can use it for progress bars.

### `chunk`

```json
{
  "type": "chunk",
  "index": 0,
  "chars": 318,
  "split_reason": "sentence",
  "synthesis_seconds": 1.42,
  "duration_seconds": 8.21,
  "rtf": 0.17,
  "audio_base64": "UklGRg..."
}
```

- `index` — zero-based, monotonically increasing, no gaps.
- `chars` — character count of the chunk's source text.
- `split_reason` — boundary used for the cut: one of `single`, `paragraph`, `sentence`, `strong`, `comma`, `space`, `hard`. Mostly diagnostic.
- `synthesis_seconds` — wall time the server spent synthesizing this chunk.
- `duration_seconds` — playback length of the chunk audio.
- `rtf` — real-time factor (`synthesis / duration`). Below 1.0 means Piper is faster than realtime on this hardware; above 1.0 means the server can't keep up with playback. Useful for capacity planning.
- `audio_base64` — complete WAV (RIFF header + samples), base64-encoded. Decode to bytes and play.

Source text is omitted by default to save bandwidth. Add `?include_text=1` to the request URL to get `"text"` in each chunk event.

### `done`

```json
{"type": "done"}
```

### `error`

```json
{"type": "error", "index": 2, "message": "Piper exited with code 1"}
```

Emitted instead of `done` if synthesis fails mid-stream. The server then closes the connection.

Pre-stream errors (invalid JSON, empty text, unknown model, `chunks_enabled=false`) are returned as HTTP 4xx/5xx with a plain-text body *before* any NDJSON is written.

| Condition | HTTP | Body |
| --- | --- | --- |
| Feature disabled | 501 | `Chunked TTS is disabled` |
| Invalid JSON | 400 | text |
| Empty text | 400 | `text cannot be empty` |
| Unknown model | 400 | `Unknown model '...'. Available models: ...` |
| Body > 1 MiB | 413 | `Payload too large` |
| GUI mode (no engine) | 404 | `Engine is disabled` |

## How chunks are sized

The server reads three numbers from env at startup:

```env
PIPER_CHUNK_TARGET_CHARS=350   # preferred chunk size
PIPER_CHUNK_MIN_CHARS=120      # never go smaller (when possible)
PIPER_CHUNK_MAX_CHARS=700      # never go larger (when possible)
```

The splitter:

1. Splits input on blank lines into paragraphs.
2. Packs paragraphs into the current chunk while the running length stays close to `target`.
3. If adding the next paragraph would overflow `target` significantly, emits the current chunk and starts a new one.
4. If a single paragraph exceeds `max`, recurses on sentence boundaries (`.!?`), then strong separators (`;:`), then commas, then whitespace, then a hard cut at `max` as last resort.

You can tune the numbers for your latency vs prosody trade-off:

- **Lower `target`** → smaller chunks → faster first audio, more chunk-boundary pauses.
- **Higher `target`** → fewer chunks → smoother prosody, slower first audio.

The defaults (350/120/700) are a balanced midpoint for Spanish-medium voices on commodity CPUs.

## Time-to-first-audio (TTFA) estimation

For a given hardware (read `rtf` from a few chunks):

```text
TTFA ≈ synthesis_seconds(chunk_0) + network_roundtrip
     ≈ chars(chunk_0) × rtf / chars_per_audio_second
```

If first-chunk latency dominates your UX, reduce `PIPER_CHUNK_TARGET_CHARS` and re-measure.

## Cancellation

The server has no cancel endpoint. To abort mid-stream, just close the HTTP connection — the client controls it.

In Python:

```python
response = urllib.request.urlopen(req)
response.close()  # aborts stream; server's wfile.write() will raise BrokenPipeError on next chunk
```

In JS:

```js
const controller = new AbortController();
fetch(`${ENGINE}/speak/chunks`, { signal: controller.signal, ... });

// later
controller.abort();
```

The server will get a write error on the next event and stop processing further chunks (its `wfile.write` raises, the handler exits). No leaked threads or processes.

## Backpressure

The server flushes every event immediately. If the client is slow to consume, the kernel's socket send buffer eventually fills and `wfile.write` blocks until the client drains. This naturally limits server-side memory pressure to one chunk's worth of WAV in flight (~hundreds of KB).

You don't need to throttle anything client-side beyond playback queue management.

## When NOT to use chunks

- **Text < ~300 chars** — overhead dominates; chunk 0 is the whole thing anyway.
- **Pre-generating audio for caching** — you want one WAV file, not N. Use `/speak`.
- **Strict gapless prosody requirements** — even gapless playback in the browser can introduce subtle artifacts at chunk boundaries. For studio-quality output, prefer `/speak`.
- **Clients that cannot stream HTTP responses** — some restricted runtimes buffer the entire body before exposing it. Test with a proxy in the path before deploying.

## When chunked makes a real difference

- **Conversational LLM agents** that speak responses as the user reads (see [05-chat-with-voice.md](05-chat-with-voice.md)).
- **Audiobook-style readers** with long paragraphs.
- **Accessibility narrators** where waiting 10 seconds before the first word is unacceptable.
- **Mobile clients on slow networks** — each chunk is much smaller than a full long-paragraph WAV.

## Verifying real streaming end-to-end

If you suspect a proxy is buffering, run this from the same network the affected client uses:

```bash
curl -N -X POST https://tts.example.com/speak/chunks \
  -H 'Content-Type: application/json' \
  -d '{"text":"'"$(printf '%.0sUna frase. ' {1..30})"'","model":"es_MX-ald-medium"}' \
| while IFS= read -r line; do
    printf '[%(%H:%M:%S.%3N)T] %s\n' -1 "${line:0:80}..."
done
```

If timestamps space out (one chunk every second or two), streaming works end-to-end. If they all share a timestamp at the end, a proxy is buffering — fix proxy config (`proxy_buffering off` in nginx, equivalent in Traefik/Caddy/CF).
