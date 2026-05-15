import re

import pytest

from piper_sandbox.chunks import ChunkConfig, split_text


SMALL = ChunkConfig(target_chars=100, min_chars=30, max_chars=200)
TINY = ChunkConfig(target_chars=50, min_chars=20, max_chars=80)
HARD = ChunkConfig(target_chars=30, min_chars=10, max_chars=40)


def _whitespace_normalized(text: str) -> str:
    return re.sub(r"\s+", "", text.replace("\r\n", "\n").replace("\r", "\n").strip())


def test_short_text_returns_single_chunk():
    chunks = split_text("Hola mundo.", SMALL)
    assert len(chunks) == 1
    assert chunks[0].split_reason == "single"
    assert chunks[0].text == "Hola mundo."
    assert chunks[0].chars == len("Hola mundo.")
    assert chunks[0].index == 0


def test_three_short_paragraphs_below_target_become_one_chunk():
    text = "Primer parrafo corto.\n\nSegundo parrafo corto.\n\nTercero corto."
    assert len(text) <= SMALL.target_chars
    chunks = split_text(text, SMALL)
    assert len(chunks) == 1
    assert chunks[0].split_reason == "single"
    assert chunks[0].text == text


def test_fourth_paragraph_overflowing_target_starts_new_chunk():
    text = (
        "Primer parrafo corto.\n\n"
        "Segundo parrafo corto.\n\n"
        "Tercero corto.\n\n"
        "Cuarto parrafo bastante mas largo que los anteriores para forzar nuevo chunk."
    )
    chunks = split_text(text, SMALL)
    assert len(chunks) >= 2
    assert chunks[0].split_reason == "paragraph"
    assert "Primer parrafo" in chunks[0].text
    assert "Tercero corto." in chunks[0].text
    assert "Cuarto parrafo" not in chunks[0].text
    assert "Cuarto parrafo" in chunks[1].text


def test_long_sentence_over_max_splits_at_comma():
    body = ", ".join(f"item-{i}" for i in range(40))
    text = body + " final"
    assert len(text) > TINY.max_chars
    chunks = split_text(text, TINY)
    assert len(chunks) >= 2
    assert chunks[0].split_reason == "comma"
    assert chunks[0].text.endswith(","), "boundary punctuation stays attached"
    assert not chunks[1].text.startswith((" ", ",")), "next chunk has no leading whitespace/sep"


def test_text_with_no_punctuation_splits_at_whitespace():
    text = " ".join(f"palabra{i}" for i in range(60))
    assert len(text) > TINY.max_chars
    chunks = split_text(text, TINY)
    assert len(chunks) >= 2
    assert chunks[0].split_reason == "space"
    assert " " not in chunks[0].text[-1:]


def test_text_with_no_whitespace_is_hard_split():
    text = "A" * 100
    chunks = split_text(text, HARD)
    assert chunks[0].split_reason == "hard"
    assert chunks[0].chars == HARD.max_chars


def test_order_preserved_modulo_whitespace():
    text = (
        "Uno.\n\nDos, tres, cuatro, cinco, seis, siete, ocho, nueve.\n\n"
        + "Diez " * 30
        + "\n\nFin."
    )
    chunks = split_text(text, SMALL)
    joined = "".join(c.text for c in chunks)
    assert _whitespace_normalized(joined) == _whitespace_normalized(text)


def test_no_empty_chunks():
    text = "Una.\n\n\n\nDos.\n\n\n\nTres.\n\n\n\nCuatro.\n\nCinco.\n\nSeis."
    chunks = split_text(text, TINY)
    assert all(c.text.strip() for c in chunks)
    assert all(c.chars > 0 for c in chunks)


def test_chars_matches_text_length():
    text = (
        "Texto medianamente largo. " * 25
        + "\n\n"
        + "Segundo parrafo con varias frases. " * 10
    )
    chunks = split_text(text, SMALL)
    for chunk in chunks:
        assert chunk.chars == len(chunk.text)


def test_crlf_produces_same_chunks_as_lf():
    text_lf = "Uno.\n\nDos.\n\nTres."
    text_crlf = text_lf.replace("\n", "\r\n")
    a = split_text(text_lf, SMALL)
    b = split_text(text_crlf, SMALL)
    assert [c.text for c in a] == [c.text for c in b]
    assert [c.split_reason for c in a] == [c.split_reason for c in b]


def test_empty_input_raises_value_error():
    with pytest.raises(ValueError):
        split_text("", SMALL)


def test_whitespace_only_input_raises_value_error():
    with pytest.raises(ValueError):
        split_text("   \n\n\t  ", SMALL)


def test_indexes_are_sequential():
    text = "Uno. " * 50 + "\n\n" + "Dos. " * 50 + "\n\n" + "Tres. " * 50
    chunks = split_text(text, SMALL)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_invalid_config_rejected():
    with pytest.raises(ValueError):
        ChunkConfig(target_chars=100, min_chars=200, max_chars=300)
    with pytest.raises(ValueError):
        ChunkConfig(target_chars=0, min_chars=0, max_chars=0)
    with pytest.raises(ValueError):
        ChunkConfig(target_chars=300, min_chars=50, max_chars=200)


def test_oversized_paragraph_splits_inside_itself():
    sentence = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    text = sentence * 8
    chunks = split_text(text, TINY)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.chars <= TINY.max_chars or chunk.split_reason == "hard"


def test_chunk_lengths_respect_min_target_max_where_practical():
    text = " ".join("Frase de prueba." for _ in range(80))
    chunks = split_text(text, SMALL)
    for chunk in chunks[:-1]:
        assert chunk.chars <= SMALL.max_chars
        assert chunk.chars >= SMALL.min_chars or chunk.split_reason == "hard"
