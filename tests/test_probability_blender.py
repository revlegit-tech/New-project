from __future__ import annotations

from mlb_app.ml.inference.probability_blender import BlendInputs, ProbabilityBlender


def test_shadow_model_is_preview_only_in_blender() -> None:
    result = ProbabilityBlender().blend(
        BlendInputs(
            model_probability=0.99,
            market_probability=0.52,
            context_probability=0.55,
            model_status="shadow",
            production_eligible=False,
        ),
        existing_final_probability_percent=52.0,
    )

    assert result.blended_probability is not None
    assert result.model_contributed is False
    assert result.final_probability_percent == 52.0
    assert any("preview-only" in warning for warning in result.warnings)


def test_production_model_contributes_to_final_blend() -> None:
    result = ProbabilityBlender().blend(
        BlendInputs(
            model_probability=0.58,
            market_probability=0.52,
            context_probability=0.55,
            engine_probability=0.54,
            steam_probability=0.51,
            model_status="production",
            production_eligible=True,
        ),
        existing_final_probability_percent=52.0,
    )

    assert result.model_contributed is True
    assert result.final_probability_percent is not None
    assert result.final_probability_percent != 52.0
    assert result.edge is not None


def test_blender_renormalizes_available_inputs() -> None:
    result = ProbabilityBlender().blend(
        BlendInputs(
            market_probability=0.52,
            context_probability=0.56,
        )
    )

    assert result.blended_probability == 0.537778
    assert result.weights_used == {"market": 0.555556, "context": 0.444444}
