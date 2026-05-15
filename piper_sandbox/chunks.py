"""Pure text splitting for chunked TTS. No HTTP, no Piper, no I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass


SplitReason = str  # "single" | "paragraph" | "sentence" | "strong" | "comma" | "space" | "hard"


@dataclass(frozen=True)
class ChunkConfig:
    target_chars: int
    min_chars: int
    max_chars: int

    def __post_init__(self) -> None:
        if self.min_chars <= 0 or self.target_chars <= 0 or self.max_chars <= 0:
            raise ValueError("min_chars, target_chars, max_chars must be positive")
        if not (self.min_chars <= self.target_chars <= self.max_chars):
            raise ValueError("require min_chars <= target_chars <= max_chars")


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    chars: int
    split_reason: SplitReason


_PARAGRAPH_SPLIT = re.compile(r"\n{2,}")
_BOUNDARY_LEVELS: tuple[tuple[str, str], ...] = (
    ("sentence", ".!?"),
    ("strong", ";:"),
    ("comma", ","),
)


def split_text(text: str, config: ChunkConfig) -> list[TextChunk]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise ValueError("text cannot be empty")

    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(normalized) if p.strip()]

    pieces: list[tuple[str, SplitReason]] = []
    current = ""

    for paragraph in paragraphs:
        if not current:
            if len(paragraph) > config.max_chars:
                pieces.extend(_split_oversized(paragraph, config))
            else:
                current = paragraph
            continue

        candidate = f"{current}\n\n{paragraph}"
        if len(candidate) <= config.target_chars:
            current = candidate
            continue

        if len(current) >= config.min_chars:
            pieces.append((current, "paragraph"))
            current = ""
            if len(paragraph) > config.max_chars:
                pieces.extend(_split_oversized(paragraph, config))
            else:
                current = paragraph
            continue

        if len(candidate) <= config.max_chars:
            current = candidate
            continue

        pieces.append((current, "paragraph"))
        current = ""
        if len(paragraph) > config.max_chars:
            pieces.extend(_split_oversized(paragraph, config))
        else:
            current = paragraph

    if current:
        pieces.append((current, "paragraph"))

    if len(pieces) == 1:
        only_text, _ = pieces[0]
        pieces = [(only_text, "single")]

    return [
        TextChunk(index=i, text=t, chars=len(t), split_reason=r)
        for i, (t, r) in enumerate(pieces)
    ]


def _split_oversized(text: str, config: ChunkConfig) -> list[tuple[str, SplitReason]]:
    pieces: list[tuple[str, SplitReason]] = []
    remaining = text
    while len(remaining) > config.max_chars:
        cut, reason = _find_split(remaining, config)
        left = remaining[:cut].rstrip()
        if left:
            pieces.append((left, reason))
        remaining = remaining[cut:].lstrip()
        if not remaining:
            return pieces
    if remaining:
        pieces.append((remaining, "paragraph"))
    return pieces


def _find_split(text: str, config: ChunkConfig) -> tuple[int, SplitReason]:
    window_start = max(config.min_chars, int(config.target_chars * 0.65))
    window_end = min(len(text), config.max_chars)
    if window_start >= window_end:
        window_start = max(1, window_end - 1)

    for reason, chars in _BOUNDARY_LEVELS:
        idx = _last_index_of_any(text, chars, window_start, window_end)
        if idx is not None:
            cut = idx + 1
            while cut < len(text) and text[cut] in " \t\n":
                cut += 1
            return cut, reason

    space_idx = text.rfind(" ", window_start, window_end)
    if space_idx > 0:
        return space_idx + 1, "space"

    return window_end, "hard"


def _last_index_of_any(text: str, chars: str, start: int, end: int) -> int | None:
    for i in range(end - 1, start - 1, -1):
        if text[i] in chars:
            return i
    return None
