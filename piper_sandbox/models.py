from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    name: str
    language: str
    country: str
    quality: str
    onnx_url: str
    json_url: str


HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

MODELS: dict[str, ModelSpec] = {
    "es_MX-claude-high": ModelSpec(
        name="es_MX-claude-high",
        language="es",
        country="MX",
        quality="high",
        onnx_url=f"{HF_BASE}/es/es_MX/claude/high/es_MX-claude-high.onnx",
        json_url=f"{HF_BASE}/es/es_MX/claude/high/es_MX-claude-high.onnx.json",
    ),
    "es_MX-ald-medium": ModelSpec(
        name="es_MX-ald-medium",
        language="es",
        country="MX",
        quality="medium",
        onnx_url=f"{HF_BASE}/es/es_MX/ald/medium/es_MX-ald-medium.onnx",
        json_url=f"{HF_BASE}/es/es_MX/ald/medium/es_MX-ald-medium.onnx.json",
    ),
    "es_ES-carlfm-x_low": ModelSpec(
        name="es_ES-carlfm-x_low",
        language="es",
        country="ES",
        quality="x_low",
        onnx_url=f"{HF_BASE}/es/es_ES/carlfm/x_low/es_ES-carlfm-x_low.onnx",
        json_url=f"{HF_BASE}/es/es_ES/carlfm/x_low/es_ES-carlfm-x_low.onnx.json",
    ),
}

DEFAULT_MODEL = "es_MX-ald-medium"


def get_model_spec(name: str) -> ModelSpec:
    try:
        return MODELS[name]
    except KeyError as exc:
        available = ", ".join(sorted(MODELS))
        raise KeyError(f"Unknown model {name!r}. Available models: {available}") from exc
