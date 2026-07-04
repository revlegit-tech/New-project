from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "scripts" / "run_mlb_full_daily_pipeline.ps1"
START_APP = ROOT / "scripts" / "start_mlb_app.ps1"
GITIGNORE = ROOT / ".gitignore"
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


def test_app_health_checker_uses_api_health_as_readiness_gate() -> None:
    source = _pipeline_source()

    assert '$probes = @("/api/health")' in source
    assert "[int]$response.StatusCode -eq 200" in source
    startup_source = source[source.index("function Start-App-IfNeeded") :]
    assert "Invoke-AppHealthProbe" in startup_source
    assert "Invoke-AppHealthProbe -AllowDocsFallback" not in startup_source
    assert '"/docs"' not in startup_source


def test_app_startup_avoids_duplicate_server_when_already_healthy() -> None:
    source = _pipeline_source()

    healthy_check = "$health = Invoke-AppHealthProbe"
    assert healthy_check in source
    assert source.index("if ($health.healthy)") < source.index("Start-Process -FilePath $python")
    assert "App already healthy" in source
    assert "Port $Port has active LISTEN process(es)" in source


def test_port_owner_detection_only_counts_listen_sockets_with_real_processes() -> None:
    source = _pipeline_source()

    assert "Get-NetTCPConnection -LocalPort $Port -State Listen" in source
    assert "OwningProcess -and [int]$_.OwningProcess -ne 0" in source
    assert "LISTENING" in source
    assert "Select-String \":$Port\\s\"" not in source
    assert "TIME_WAIT" not in source


def test_unhealthy_listener_requires_explicit_force_before_kill() -> None:
    source = _pipeline_source()

    assert "[switch]$ForcePortRelease" in source
    assert "Use -ForcePortRelease only when you intentionally want this script to stop" in source
    assert "if (-not $ForcePortRelease)" in source
    assert source.index("if (-not $ForcePortRelease)") < source.index("Stop-Process -Id $listener.Pid -Force")


def test_failed_readiness_reports_http_error_and_port_owner() -> None:
    source = _pipeline_source()

    assert "Last readiness probe: endpoint=$($health.endpoint) status=$($health.statusCode) error=$($health.error)" in source
    assert "Get-PortOwnerSummary -Port $Port" in source
    assert "Port $Port owner: $owner" in source


def test_launchers_validate_venv_and_uvicorn_with_rebuild_guidance() -> None:
    pipeline = _pipeline_source()
    start_app = START_APP.read_text(encoding="utf-8")

    for source in (pipeline, start_app):
        assert ".venv\\Scripts\\python.exe" in source
        assert "import sys; print(sys.executable)" in source
        assert "import uvicorn; print(uvicorn.__name__)" in source
        assert "py -3 -m venv .\\.venv" in source
        assert ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt" in source


def test_generated_runtime_artifacts_have_narrow_gitignore_entries() -> None:
    source = GITIGNORE.read_text(encoding="utf-8")

    for entry in (
        "data/backtests/player_prop_model_backtest_2026.csv",
        "data/backtests/player_prop_model_backtest_summary_2026.json",
        "data/context/",
        "data/training/historical_props_from_ml_labels_joined.csv",
        "data/training/historical_props_from_ml_labels_joined_summary.json",
        "data/training/player_prop_labels_2026.csv",
    ):
        assert entry in source


def test_scoring_research_lock_remains_intact() -> None:
    source = SCORING_SERVICE.read_text(encoding="utf-8")

    assert '"action": "Research"' in source
    assert '"stakeUnits": 0' in source
    assert "betActionAllowed" in source
    assert "gate.betActionAllowed" in source
