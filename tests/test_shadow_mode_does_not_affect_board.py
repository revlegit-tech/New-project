from __future__ import annotations

from mlb_app.ml.inference.probability_blender import BlendInputs, ProbabilityBlender


def test_shadow_model_never_alters_production_final_probability() -> None:
    result = ProbabilityBlender().blend(
        BlendInputs(model_probability=0.99, market_probability=0.5, model_status="shadow", production_eligible=False),
        existing_final_probability_percent=52.0,
    )

    assert result.model_contributed is False
    assert result.final_probability_percent == 52.0


def test_production_model_can_alter_final_probability_only_when_gated() -> None:
    blocked = ProbabilityBlender().blend(
        BlendInputs(model_probability=0.8, market_probability=0.5, model_status="production", production_eligible=False),
        existing_final_probability_percent=52.0,
    )
    allowed = ProbabilityBlender().blend(
        BlendInputs(model_probability=0.8, market_probability=0.5, model_status="production", production_eligible=True),
        existing_final_probability_percent=52.0,
    )

    assert blocked.model_contributed is False
    assert blocked.final_probability_percent == 52.0
    assert allowed.model_contributed is True
    assert allowed.final_probability_percent != 52.0
