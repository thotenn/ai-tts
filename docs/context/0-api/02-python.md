# 02 — Python Client Recipes

All examples use stdlib `urllib` so they run without extra dependencies. Adapt to `requests`/`httpx` if you already use them.

## Synthesize one phrase

```python
import json
import urllib.request

ENGINE = "https://tts.example.com"

def synthesize(text: str, model: str = "es_MX-ald-medium") -> bytes:
    req = urllib.request.Request(
        f"{ENGINE}/speak",
        data=json.dumps({"text": text, "model": model}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read()

wav = synthesize("Hola mundo")
with open("salida.wav", "wb") as f:
    f.write(wav)
```

## Consume the chunked stream

The endpoint returns NDJSON. Parse line by line and decode each `audio_base64`.

```python
import base64
import json
import urllib.request

ENGINE = "https://tts.example.com"


def synthesize_chunks(text: str, model: str = "es_MX-ald-medium"):
    req = urllib.request.Request(
        f"{ENGINE}/speak/chunks",
        data=json.dumps({"text": text, "model": model}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        for raw in response:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            event = json.loads(line)
            if event["type"] == "chunk":
                event["audio"] = base64.b64decode(event["audio_base64"])
                del event["audio_base64"]
            yield event


for event in synthesize_chunks("Un parrafo largo..."):
    if event["type"] == "meta":
        print(f"planned {event['chunks']} chunks")
    elif event["type"] == "chunk":
        print(f"chunk {event['index']}: {len(event['audio'])} bytes, rtf={event['rtf']}")
    elif event["type"] == "error":
        raise RuntimeError(event["message"])
```

The generator yields events as they arrive — chunk 0 is available before chunk N has been synthesized.

## Reusable client class

Drop this into your project and call methods. Includes retries, timeouts and a chunked iterator.

```python
import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterator, Optional


@dataclass
class ChunkEvent:
    type: str
    index: Optional[int] = None
    audio: Optional[bytes] = None
    chars: Optional[int] = None
    duration_seconds: Optional[float] = None
    synthesis_seconds: Optional[float] = None
    rtf: Optional[float] = None
    split_reason: Optional[str] = None
    message: Optional[str] = None
    raw: Optional[dict] = None


class PiperClient:
    def __init__(self, base_url: str, *, default_model: Optional[str] = None,
                 timeout: int = 180, retries: int = 1):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self.retries = retries

    def health(self) -> dict:
        return self._get_json("/health")

    def models(self) -> dict:
        return self._get_json("/models")

    def speak(self, text: str, model: Optional[str] = None) -> bytes:
        body = {"text": text, "model": model or self.default_model}
        return self._post_bytes("/speak", body)

    def speak_chunks(self, text: str, model: Optional[str] = None) -> Iterator[ChunkEvent]:
        body = {"text": text, "model": model or self.default_model}
        request = self._build_post("/speak/chunks", body)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            for raw in response:
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                event = json.loads(line)
                audio = None
                if event["type"] == "chunk":
                    audio = base64.b64decode(event["audio_base64"])
                yield ChunkEvent(
                    type=event["type"],
                    index=event.get("index"),
                    audio=audio,
                    chars=event.get("chars"),
                    duration_seconds=event.get("duration_seconds"),
                    synthesis_seconds=event.get("synthesis_seconds"),
                    rtf=event.get("rtf"),
                    split_reason=event.get("split_reason"),
                    message=event.get("message"),
                    raw=event,
                )

    def _get_json(self, path: str) -> dict:
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(f"{self.base_url}{path}", timeout=self.timeout) as r:
                    return json.loads(r.read())
            except urllib.error.URLError:
                if attempt == self.retries:
                    raise
                time.sleep(0.5 * (attempt + 1))

    def _post_bytes(self, path: str, body: dict) -> bytes:
        request = self._build_post(path, body)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read()

    def _build_post(self, path: str, body: dict) -> urllib.request.Request:
        return urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
```

Usage:

```python
piper = PiperClient("https://tts.example.com", default_model="es_MX-ald-medium")

# One-shot
wav = piper.speak("Una frase corta.")
open("out.wav", "wb").write(wav)

# Streaming
for event in piper.speak_chunks("Un parrafo largo..."):
    if event.type == "chunk":
        open(f"chunk_{event.index}.wav", "wb").write(event.audio)
```

## Save streamed audio as one concatenated WAV

You can join successive WAV chunks but it requires stripping every chunk's RIFF header except the first and rewriting the size fields. Easier: keep them as separate files and play in order, or transcode with ffmpeg:

```python
import subprocess

paths = ["chunk_0.wav", "chunk_1.wav", "chunk_2.wav"]
listfile = "list.txt"
with open(listfile, "w") as f:
    for p in paths:
        f.write(f"file '{p}'\n")
subprocess.run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", listfile,
                "-c", "copy", "joined.wav"], check=True)
```

## Synchronous playback while streaming

Combine the streaming iterator with a simple audio player so playback starts on chunk 0:

```python
import subprocess
import tempfile
import threading
from queue import Queue


def play_streamed(client: PiperClient, text: str, model: Optional[str] = None,
                  player: str = "ffplay"):
    queue: Queue = Queue()
    done = threading.Event()

    def producer():
        try:
            for event in client.speak_chunks(text, model=model):
                if event.type == "chunk":
                    queue.put(event.audio)
                elif event.type == "error":
                    raise RuntimeError(event.message)
        finally:
            done.set()
            queue.put(None)  # sentinel

    def consumer():
        while True:
            wav = queue.get()
            if wav is None:
                if done.is_set():
                    return
                continue
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(wav)
                tmp_path = tmp.name
            subprocess.run([player, "-nodisp", "-autoexit", "-loglevel", "quiet",
                            tmp_path], check=False)

    t = threading.Thread(target=producer, daemon=True)
    t.start()
    consumer()
    t.join()


play_streamed(piper, "Un parrafo largo...")
```

This blocks the calling thread while playing. For async/UI contexts use `asyncio` and `aiohttp` instead — same algorithm, different plumbing.

## Async with `httpx` (optional)

If you prefer async:

```python
import asyncio
import base64
import httpx


async def synthesize_chunks_async(text: str, model: str = "es_MX-ald-medium"):
    async with httpx.AsyncClient(timeout=180) as client:
        async with client.stream(
            "POST",
            "https://tts.example.com/speak/chunks",
            json={"text": text, "model": model},
        ) as response:
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                event = httpx._utils.json.loads(line)
                if event["type"] == "chunk":
                    event["audio"] = base64.b64decode(event["audio_base64"])
                yield event


async def main():
    async for event in synthesize_chunks_async("Texto largo..."):
        print(event["type"])


asyncio.run(main())
```
