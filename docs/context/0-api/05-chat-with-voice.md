# 05 — Chat With Voice

Integration patterns for combining an LLM with Piper TTS, ordered from simplest to most responsive.

The LLM provider is abstracted as `ask_llm(prompt) -> str` or `stream_llm(prompt) -> Iterator[str]`. Use OpenAI, Anthropic, a local Llama, whatever — the TTS half is identical.

## Pattern A — Speak the final answer

Simplest. User asks, you wait for the LLM, you synthesize the answer, you play it.

```python
def chat_and_speak(prompt: str, piper: PiperClient):
    answer = ask_llm(prompt)             # blocks until LLM done
    wav = piper.speak(answer)            # blocks until TTS done
    play(wav)                            # blocks until playback done
```

**Latency**: `LLM_time + TTS_time` before the first audible word. Acceptable for one-shot Q&A, awful for conversations.

When to use: batch scripts, voicemail-style replies, anything non-interactive.

## Pattern B — Speak each LLM sentence as it lands

Stream tokens from the LLM, accumulate until you hit a sentence terminator, send that sentence through `/speak` and play. Don't wait for the next sentence to start playing the current one.

```python
import re

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def chat_and_speak_sentences(prompt: str, piper: PiperClient):
    buffer = ""
    audio_queue = ThreadSafeQueue()
    play_thread = start_background_player(audio_queue)

    for token in stream_llm(prompt):
        buffer += token
        # split on sentence boundaries
        while True:
            match = SENTENCE_END.search(buffer)
            if not match:
                break
            sentence, buffer = buffer[:match.end()], buffer[match.end():]
            sentence = sentence.strip()
            if sentence:
                wav = piper.speak(sentence)
                audio_queue.put(wav)

    # flush trailing text without terminator
    tail = buffer.strip()
    if tail:
        audio_queue.put(piper.speak(tail))

    audio_queue.put(None)  # sentinel
    play_thread.join()
```

**Latency**: time-to-first-audio = `LLM_first_sentence_time + TTS(first_sentence)`. Often 1-3 seconds for short sentences — usable for live chat.

**Caveat**: prosody is sentence-by-sentence; you lose intonation continuity. For short conversational replies that's fine; for narration it sounds choppy.

## Pattern C — Pipeline LLM streaming into `/speak/chunks`

When the LLM answer is paragraph-length and you want chunked TTS to take over splitting, accumulate the full answer (or a paragraph) and send to `/speak/chunks`. You get the best prosody (the splitter sees sentence context) and chunk 0 still lands quickly.

```python
def chat_and_stream_chunks(prompt: str, piper: PiperClient):
    answer = ask_llm(prompt)             # wait for full answer
    audio_queue = ThreadSafeQueue()
    player = start_background_player(audio_queue)

    for event in piper.speak_chunks(answer):
        if event.type == "chunk":
            audio_queue.put(event.audio)
        elif event.type == "error":
            print(f"TTS error: {event.message}")
            break

    audio_queue.put(None)
    player.join()
```

**Latency**: `LLM_time + TTS(chunk_0)`. The LLM full-wait is the bottleneck.

**Improvement**: if your LLM streams *paragraphs*, send each paragraph through `/speak/chunks` as it completes. You get the LLM's first paragraph speaking while the LLM is still producing the second.

## Pattern D — Browser-side, conversational

End-to-end in the browser. LLM streams over SSE/WebSocket, Piper streams over `/speak/chunks`. The user sees text appearing as it's being spoken.

```js
async function converse(prompt) {
  const audio = new Audio();
  const queue = [];
  let playing = false;

  const playNext = () => {
    const blob = queue.shift();
    if (!blob) { playing = false; return; }
    audio.src = URL.createObjectURL(blob);
    audio.onended = playNext;
    audio.play();
    playing = true;
  };

  const speakSentence = async (sentence) => {
    const r = await fetch(`${ENGINE}/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: sentence, model: "es_MX-ald-medium" }),
    });
    if (!r.ok) return;
    queue.push(await r.blob());
    if (!playing) playNext();
  };

  // Stream LLM tokens, buffer per sentence, kick off TTS as each sentence completes.
  let buf = "";
  for await (const token of streamLLM(prompt)) {
    appendToTranscript(token);   // your UI update
    buf += token;
    const match = buf.match(/(.+?[.!?])\s+/);
    if (match) {
      speakSentence(match[1]);
      buf = buf.slice(match[0].length);
    }
  }
  if (buf.trim()) speakSentence(buf.trim());
}
```

This is the "ChatGPT voice mode" pattern: text appears in real time AND audio comes out in real time AND it sounds natural enough because each sentence has prosody continuity.

## Choosing between B and D

| Scenario | Use |
| --- | --- |
| Conversation with quick replies | B (Python) or D (browser) — sentence-level TTS |
| Long-form narration | C — single `/speak/chunks` call per paragraph |
| Realtime voice agent | D — browser-side both streams |

## Caching for repeat phrases

If your app says the same thing often ("How can I help you today?"), cache the WAV by hash:

```python
import hashlib

class CachedPiper:
    def __init__(self, client: PiperClient, cache_dir: str = ".tts-cache"):
        self.client = client
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

    def speak(self, text: str, model: str = "es_MX-ald-medium") -> bytes:
        key = hashlib.sha256(f"{model}::{text}".encode()).hexdigest()[:16]
        path = self.cache_dir / f"{key}.wav"
        if path.exists():
            return path.read_bytes()
        wav = self.client.speak(text, model=model)
        path.write_bytes(wav)
        return wav
```

Cuts response time to near-zero for repeat phrases. Combine with sentence-level chunking for canned greetings + dynamic content mid-conversation.

## Multi-voice dialogue

If your app has multiple speakers (e.g. a podcast generator), pick a different model per turn:

```python
voices = {
    "host": "es_MX-claude-high",
    "guest": "es_MX-ald-medium",
}

for turn in script:
    wav = piper.speak(turn["line"], model=voices[turn["speaker"]])
    audio_queue.put(wav)
```

Mix-and-match is trivial because each request is stateless.

## Concurrent requests

The engine handles requests in threads, but synthesis itself is CPU-bound. Sending N requests in parallel doesn't make any single one faster, and risks saturating the CPU. For interactive use, one request at a time per user is the right default. For batch jobs, set a worker pool sized to (cores - 1) on the engine side.

## Production sketch: voice-enabled chatbot

Putting it together (Python, server-side):

```python
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import threading


class VoiceChatbot:
    def __init__(self, llm, piper: PiperClient, audio_sink):
        self.llm = llm
        self.piper = piper
        self.audio_sink = audio_sink  # async-safe consumer (websocket, file, speaker...)
        self.tts_pool = ThreadPoolExecutor(max_workers=2)

    def reply(self, user_text: str):
        buf = ""
        order = 0
        futures = {}

        for token in self.llm.stream(user_text):
            buf += token
            match = SENTENCE_END.search(buf)
            if match:
                sentence, buf = buf[:match.end()], buf[match.end():]
                fut = self.tts_pool.submit(self.piper.speak, sentence.strip())
                futures[order] = fut
                order += 1

        if buf.strip():
            futures[order] = self.tts_pool.submit(self.piper.speak, buf.strip())

        # Drain in order so audio is concatenated correctly.
        for i in sorted(futures):
            try:
                wav = futures[i].result(timeout=60)
                self.audio_sink.write(wav)
            except Exception as exc:
                self.audio_sink.write_error(str(exc))
```

The TTS pool lets sentence N+1 start synthesizing while the audio sink is still consuming sentence N — total throughput goes up without sacrificing playback order.

Adapt `audio_sink` to your transport:
- Websocket → binary frames.
- File → temp wav chunks plus an index for playback.
- Phone (Twilio) → mulaw transcode + media stream.
- Discord bot → push to voice channel.

The piece that doesn't change is the TTS contract.
