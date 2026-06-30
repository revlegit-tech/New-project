from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "scripts" / "run_mlb_full_daily_pipeline.ps1"
SCORING_SERVICE = ROOT / "mlb_app" / "services" / "player_prop_model_scoring_service.py"


def _pipeline_source() -> str:
    return PIPELINE.read_text(encoding="utf-8")


def test_full_daily_pipeline_materializes_context_sources_before_scoring() -> None:
    source = _pipeline_source()

    assert 'Invoke-Step "Context source materialization"' in source
    assert ".\\scripts\\materialize_context_sources.py" in source or "scripts\\materialize_context_sources.py" in source
    assert "--date $RunDate --season $Season" in source
    assert source.index('Invoke-Step "Context source materialization"') < source.index('Invoke-Step "Playerboard-safe model scoring"')
    assert source.index('Invoke-Step "Context source materialization"') < source.index('Invoke-Step "Feature matrix materialization"')


def test_context_materialization_stage_warns_for_optional_partial_sources() -> None:
    source = _pipeline_source()

    assert "context source script missing" in source
    assert "weather unavailable" in source
    assert "umpire neutral fallback" in source
    assert "game markets missing" in source
    assert "context source partial" in source


def test_app_health_checker_prefers_api_health_200_with_docs_fallback() -> None:
    source = _pipeline_source()

    assert '$probes = @("/api/health")' in source
    assert '$probes += "/docs"' in source
    assert "[int]$response.StatusCode -eq 200" in source
    assert source.index('"/api/health"') < source.index('"/docs"')


def test_app_startup_avoids_duplicate_server_when_already_healthy() -> None:
    source = _pipeline_source()

    healthy_check = "$health = Invoke-AppHealthProbe -AllowDocsFallback"
    assert healthy_check in source
    assert source.index("if ($health.healthy)") < source.index("Start-Process -FilePath $python")
    assert "App already healthy" in source
    assert "Port $Port is already owned by" in source


def test_failed_readiness_reports_http_error_and_port_owner() -> None:
    source = _pipeline_source()

    assert "Last readiness probe: endpoint=$($health.endpoint) status=$($health.statusCode) error=$($health.error)" in source
    assert "Get-PortOwnerSummary -Port $Port" in source
    assert "Port $Port owner: $owner" in source
    assert "Stop-Process -Id $process.Id -Force" in source


def test_scoring_research_lock_remains_intact() -> None:
    source = SCORING_SERVICE.read_text(encoding="utf-8")

    assert '"action": "Research"' in source
    assert '"stakeUnits": 0' in source
    assert "betActionAllowed" in source
    assert "gate.betActionAllowed" in source
