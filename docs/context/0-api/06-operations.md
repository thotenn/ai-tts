# 06 — Operations

Things you'll want to know once the API leaves your laptop.

## CORS

Controlled by `PIPER_CORS_ORIGIN` on the engine. Default is `*` (any origin).

| Value | Effect |
| --- | --- |
| `*` | Any browser origin can hit the API. Fine for personal use, not for prod with multi-tenant secrets. |
| `https://app.example.com` | Only that single origin is allowed. Other origins fail preflight. |
| `` (empty) | No CORS headers sent — same-origin only. Useful when the API is fronted by your app on the same domain. |

The current code supports exactly one value. If you need a whitelist, put a reverse proxy in front that rewrites the `Access-Control-Allow-Origin` header dynamically based on the incoming `Origin`.

Preflight is handled automatically for `Content-Type: application/json` POSTs.

## Authentication

Built-in: **none**. The API is wide open. If you publish the URL, anyone can use your CPU to synthesize audio.

Cheap options to gate access:

1. **Reverse proxy basic auth.** nginx/Caddy/Traefik can require `Authorization: Basic ...` on every request. Tradeoff: your clients (browser app, scripts) all need to send credentials.

2. **Static API key in a header.** Same proxy enforces a single shared secret:

   ```nginx
   if ($http_x_api_key != "your-secret-token") {
     return 401;
   }
   ```

   Clients send `X-Api-Key: your-secret-token`. Easy and adequate for personal projects.

3. **Cloudflare Access / Authelia / OAuth proxy** in front for proper user-level auth. Heavier setup; appropriate for serving multiple humans with separate identities.

4. **VPN / Tailscale only.** Don't expose the API on the public internet at all; only let trusted clients reach it via private network. Strongest option for personal use.

The TTS code itself stays unauthenticated — keep responsibility at the proxy layer.

## Rate limiting

Built-in: **none**. Piper is CPU-bound; one well-formed POST to `/speak/chunks` with a multi-paragraph text can pin a CPU core for ~30 seconds. A naive attacker can DoS you trivially.

Mitigations:

- **`PIPER_CORS_ORIGIN` lock-down** prevents drive-by browser usage from random websites, but not direct API hits.
- **Reverse proxy rate limit** (nginx `limit_req`, Caddy `rate_limit`, Cloudflare rules) — recommended baseline. Cap requests-per-IP-per-minute.
- **Body size limit on the proxy** — defense in depth, even though the app already enforces `MAX_REQUEST_BODY_BYTES = 1 MiB`.

Example nginx rate limit (10 req/min per IP, burst of 5):

```nginx
limit_req_zone $binary_remote_addr zone=tts:10m rate=10r/m;

location / {
  limit_req zone=tts burst=5 nodelay;
  proxy_pass http://piper:8000;
}
```

## Health checks

`GET /health` returns 200 with a small JSON body when the process is alive. Use it for:

- Docker `HEALTHCHECK` (already configured in the compose file).
- Coolify / Kubernetes / Nomad liveness probes.
- Uptime monitoring (UptimeRobot, healthchecks.io, etc.) — a 30s interval is plenty.

It does **not** verify that Piper itself is functional. To do that, periodically hit `/speak` with a short canned phrase:

```bash
# canary; expect 200 + RIFF header
curl -X POST https://tts.example.com/speak \
  -H 'Content-Type: application/json' \
  -d '{"text":"ok","model":"es_MX-ald-medium"}' \
  --max-time 30 -o /dev/null -w '%{http_code}\n'
```

If your monitor sees this fail, the binary or the model is broken.

## Reverse proxy buffering for `/speak/chunks`

The chunked endpoint depends on the proxy not buffering the response. Settings to verify per proxy:

**nginx** — disable buffering on the route:

```nginx
location /speak/chunks {
  proxy_buffering off;
  proxy_request_buffering off;
  proxy_pass http://piper:8000;
}
```

**Caddy** — disable buffering globally or per matcher:

```
@chunks path /speak/chunks
reverse_proxy /speak/chunks piper:8000 {
  flush_interval -1
}
```

**Traefik** — uses `responseForwarding.flushInterval` (set to `-1` for immediate flush; default `100ms` is usually fine but worth setting explicitly).

**Cloudflare** — by default it caches and may buffer responses with no `Content-Length`. Either set a Page Rule to bypass cache for `/speak/chunks`, or proxy through Cloudflare Workers that streams the response, or — easiest — don't put Cloudflare in front of the TTS endpoint at all.

The server already sends `X-Accel-Buffering: no`, which nginx (and several Cloudflare paths) honor automatically. Worth setting buffer-off explicitly anyway.

## Adding custom voices

A "voice" is just an entry in `PIPER_MODEL_NAMES`. The server derives the download URL from the name pattern `language_COUNTRY-voice-quality`:

```text
{PIPER_HF_BASE}/{language}/{language}_{COUNTRY}/{voice}/{quality}/{name}.onnx
```

So adding `de_DE-thorsten-medium`:

```env
PIPER_MODEL_NAMES=["es_MX-ald-medium","de_DE-thorsten-medium"]
```

Restart. The first request to the new voice triggers a one-time download from Hugging Face.

For voices not on `rhasspy/piper-voices`, host the `.onnx` and `.onnx.json` yourself and either:

- Set `PIPER_HF_BASE` to your mirror that mirrors the same directory structure, or
- Drop the files directly under `PIPER_MODELS_DIR/<name>/<name>.onnx[.json]` and they'll be picked up without download.

## Capacity planning

Per-request synthesis time scales with text length and inversely with model quality and CPU. Rule of thumb on a modern x86 core, Spanish medium voice:

- 100 chars → ~0.5 s synthesis, ~3 s audio (rtf ≈ 0.17)
- 700 chars → ~3-4 s synthesis, ~22 s audio (rtf ≈ 0.17)

ARM64 Ampere cores are slightly slower per core but you typically have more of them. Each in-flight request takes one core. The HTTP server is threaded, so N concurrent requests will use N cores.

If you need to serve many concurrent users with low latency, scale horizontally (more containers, load balancer in front) — the API is stateless apart from the on-disk model cache, which can be shared via a volume.

## Logging

The server prints request lines to stdout in BaseHTTPRequestHandler's default format:

```text
127.0.0.1 - "POST /speak/chunks HTTP/1.1" 200 -
```

Coolify aggregates container stdout. For structured logs, run behind a reverse proxy that emits structured access logs and use those — the app itself doesn't need a logging library.

## Restart behaviour

`docker compose` defaults to `restart: unless-stopped` (already set in the compose file). On crash, the container restarts and the model cache (volume) survives. First request after restart hits the disk cache, no re-download.

## Versioning the API

This API is currently unversioned. Endpoints are stable in V1; future incompatible changes would land under a `/v2/...` prefix and old paths would keep working. For now, prod clients can assume:

- `/speak` returns `audio/wav` with `text`+`model` JSON input — stable.
- `/speak/chunks` emits NDJSON with `meta`/`chunk`/`done`/`error` event shapes — stable; new optional fields may be added.
- `/health`, `/models` — stable.
- `chunk` event `text` field is opt-in via `?include_text=1`.
- Any field not documented in [04-streaming.md](04-streaming.md) is internal and may disappear.

## Common production checklist

- [ ] `PIPER_CORS_ORIGIN` restricted to your real origins.
- [ ] Reverse-proxy auth (basic, API key, or OAuth) protecting the API surface.
- [ ] Rate limit at the proxy.
- [ ] Buffering disabled for `/speak/chunks` and verified with the curl timestamp trick from [04-streaming.md](04-streaming.md).
- [ ] Health canary that exercises real Piper synthesis, not just `/health`.
- [ ] Model cache on a persistent volume.
- [ ] Memory headroom: at least 2x the largest concurrent chunk WAV (typically ~1-2 MiB per chunk × in-flight count).
