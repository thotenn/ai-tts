# 03 — JavaScript Recipes

Browser fetch + Node 18+ (which has `fetch` built in). All examples assume `ENGINE` is the engine base URL.

## Synthesize one phrase (browser)

```js
const ENGINE = "https://tts.example.com";

async function speak(text, model = "es_MX-ald-medium") {
  const response = await fetch(`${ENGINE}/speak`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, model }),
  });
  if (!response.ok) throw new Error(await response.text());
  return await response.blob();   // audio/wav blob
}

const blob = await speak("Hola mundo");
const audio = new Audio(URL.createObjectURL(blob));
await audio.play();
```

`audio.play()` requires a user gesture (click, tap, keypress) on most browsers — call it from a click handler the first time.

## Stream chunks and play in order (browser)

The reference GUI is the canonical implementation; here's a minimal version stripped of state machine bookkeeping.

```js
async function speakChunked(text, model = "es_MX-ald-medium") {
  const response = await fetch(`${ENGINE}/speak/chunks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, model }),
  });
  if (!response.ok) throw new Error(await response.text());

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const queue = [];
  let playing = false;
  let buf = "";
  const audio = new Audio();

  const playNext = () => {
    const next = queue.shift();
    if (!next) { playing = false; return; }
    audio.src = URL.createObjectURL(next);
    audio.onended = playNext;
    audio.play();
    playing = true;
  };

  const base64ToBlob = (b64) => {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: "audio/wav" });
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (!line) continue;
      const event = JSON.parse(line);
      if (event.type === "chunk") {
        queue.push(base64ToBlob(event.audio_base64));
        if (!playing) playNext();
      } else if (event.type === "error") {
        throw new Error(event.message);
      }
    }
  }
}

document.querySelector("#speak").addEventListener("click", () =>
  speakChunked("Un parrafo largo...")
);
```

Audible gaps between chunks are usually minor (~50-150 ms) because `<audio>` element switching takes a frame. If you need gapless playback see the Web Audio API section below.

## Stream chunks in Node.js

```js
async function* iterateChunks(text, model = "es_MX-ald-medium") {
  const response = await fetch("https://tts.example.com/speak/chunks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, model }),
  });
  if (!response.ok) throw new Error(await response.text());

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (!line) continue;
      const event = JSON.parse(line);
      if (event.type === "chunk") {
        event.audio = Buffer.from(event.audio_base64, "base64");
        delete event.audio_base64;
      }
      yield event;
    }
  }
}

import { writeFileSync } from "node:fs";

for await (const event of iterateChunks("Texto largo...")) {
  if (event.type === "chunk") {
    writeFileSync(`chunk_${event.index}.wav`, event.audio);
  } else if (event.type === "error") {
    throw new Error(event.message);
  }
}
```

## Gapless playback with Web Audio API

For voice apps where chunk-to-chunk gaps matter (TV-style narration, dialogue), decode each WAV and schedule it at the precise end time of the previous one:

```js
const audioCtx = new AudioContext();
let nextStartTime = 0;

async function enqueueChunk(blob) {
  const arrayBuffer = await blob.arrayBuffer();
  const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
  const source = audioCtx.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(audioCtx.destination);
  const startAt = Math.max(audioCtx.currentTime + 0.05, nextStartTime);
  source.start(startAt);
  nextStartTime = startAt + audioBuffer.duration;
}
```

Replace the `<audio>` element in `speakChunked` with calls to `enqueueChunk(blob)`. The 50 ms head-start prevents underruns on the first chunk; tune to taste.

## CORS reminder

If you hit "CORS error" from the browser, the engine's `PIPER_CORS_ORIGIN` doesn't include your origin. Either:

- Set `PIPER_CORS_ORIGIN=*` on the engine for any-origin access, or
- Set `PIPER_CORS_ORIGIN=https://your-app.example.com` to allow exactly one origin, or
- Proxy the engine through your own backend so browser → backend → engine (same-origin from the browser's view).

## Type definitions

If you use TypeScript:

```ts
type Speakable = { text: string; model?: string };

type MetaEvent = {
  type: "meta";
  model: string;
  chunks: number;
  target_chars: number;
  min_chars: number;
  max_chars: number;
};

type ChunkEvent = {
  type: "chunk";
  index: number;
  chars: number;
  split_reason: "single" | "paragraph" | "sentence" | "strong" | "comma" | "space" | "hard";
  synthesis_seconds: number;
  duration_seconds: number;
  rtf: number | null;
  audio_base64: string;
  text?: string;  // present only with ?include_text=1
};

type DoneEvent = { type: "done" };
type ErrorEvent = { type: "error"; index?: number; message: string };

type SpeakChunksEvent = MetaEvent | ChunkEvent | DoneEvent | ErrorEvent;
```
