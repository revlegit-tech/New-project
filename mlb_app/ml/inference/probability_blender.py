from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_BLEND_WEIGHTS: dict[str, float] = {
    "model": 0.35,
    "market": 0.25,
    "context": 0.20,
    "engine": 0.15,
    "steam": 0.05,
}


@dataclass(frozen=True)
class BlendInputs:
    model_probability: float | None = None
    market_probability: float | None = None
    context_probability: float | None = None
    engine_probability: float | None = None
    steam_probability: float | None = None
    model_status: str = "shadow"
    production_eligible: bool = False
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_BLEND_WEIGHTS))


@dataclass(frozen=True)
class BlendResult:
    blended_probability: float | None
    edge: float | None
    model_contributed: bool
    final_probability: float | None
    final_probability_percent: float | None
    weights_used: dict[str, float]
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "blendedProbability": self.blended_probability,
            "edge": self.edge,
            "modelContributed": self.model_contributed,
            "finalProbability": self.final_probability,
            "finalProbabilityPercent": self.final_probability_percent,
            "weightsUsed": dict(self.weights_used),
            "warnings": list(self.warnings),
        }


class ProbabilityBlender:
    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = dict(weights or DEFAULT_BLEND_WEIGHTS)

    def blend(
        self,
        inputs: BlendInputs,
        *,
        existing_final_probability_percent: float | None = None,
    ) -> BlendResult:
        weights = dict(self.weights)
        weights.update(inputs.weights or {})
        warnings: list[str] = []
        model_allowed = _is_production_model(inputs.model_status, inputs.production_eligible)
        preview_mode = not model_allowed

        components: dict[str, float] = {}
        for name, value in (
            ("model", inputs.model_probability),
            ("market", inputs.market_probability),
            ("context", inputs.context_probability),
            ("engine", inputs.engine_probability),
            ("steam", inputs.steam_probability),
        ):
            probability = _probability(value)
            if probability is None:
                continue
            if name == "model" and not model_allowed:
                if probability is not None:
                    warnings.append("model probability is preview-only until production gates pass")
                components[name] = probability
                continue
            components[name] = probability

        if not components:
            return BlendResult(
                blended_probability=None,
                edge=None,
                model_contributed=False,
                final_probability=_probability_from_percent(existing_final_probability_percent),
                final_probability_percent=existing_final_probability_percent,
                weights_used={},
                warnings=tuple(warnings or ["no probability inputs were available"]),
            )

        weighted = {name: max(float(weights.get(name, 0.0)), 0.0) for name in components}
        total_weight = sum(weighted.values())
        if total_weight <= 0:
            weighted = {name: 1.0 for name in components}
            total_weight = float(len(weighted))
            warnings.append("blend weights were empty; equal weights used")
        normalized = {name: value / total_weight for name, value in weighted.items()}
        blended = sum(components[name] * normalized[name] for name in components)
        market = _probability(inputs.market_probability)
        edge = blended - market if market is not None else None
        final_probability = blended if model_allowed else _probability_from_percent(existing_final_probability_percent)
        final_percent = round(final_probability * 100.0, 3) if final_probability is not None else existing_final_probability_percent
        if preview_mode and existing_final_probability_percent is None:
            final_percent = None

        return BlendResult(
            blended_probability=round(blended, 6),
            edge=round(edge, 6) if edge is not None else None,
            model_contributed=bool(model_allowed and "model" in components),
            final_probability=round(final_probability, 6) if final_probability is not None else None,
            final_probability_percent=final_percent,
            weights_used={name: round(value, 6) for name, value in normalized.items()},
            warnings=tuple(_dedupe(warnings)),
        )


def _is_production_model(status: str, production_eligible: bool) -> bool:
    return str(status or "").strip().lower() == "production" and bool(production_eligible)


def _probability(value: float | int | str | None) -> float | None:
    if value in {None, ""}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 1.0 and number <= 100.0:
        number = number / 100.0
    if number < 0.0 or number > 1.0:
        return None
    return number


def _probability_from_percent(value: float | int | str | None) -> float | None:
    if value in {None, ""}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0.0 or number > 100.0:
        return None
    return number / 100.0


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            out.append(text)
            seen.add(text)
    return out
