from __future__ import annotations

import csv
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.contracts.feature_store_schema import postgame_label_names, pregame_feature_names
from mlb_app.services.data_source_capability_service import resolve_date_mode
from mlb_app.services.model_training_readiness_service import ALLOWED_MODEL_STATES, ModelTrainingReadinessService
from mlb_app.services.runtime_status_service import safe_relpath

SCHEMA_VERSION = "baseline-model-training.v1"
STATUS_SCHEMA_VERSION = "baseline-model-status.v1"
SUPPORTED_BASELINE_MARKETS = frozenset({"batter_hits", "batter_total_bases", "pitcher_strikeouts"})


class BaselineModelTrainingService:
    """Explicit-only baseline trainer for research player prop models."""

    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings
        self.readiness = ModelTrainingReadinessService(settings)

    def train(
        self,
        *,
        date_label: str | None,
        season: int | None,
        market: str,
        train: bool = False,
    ) -> dict[str, Any]:
        target_date, mode = resolve_date_mode(date_label)
        selected_season = int(season or self.settings.current_season)
        selected_market = _clean(market)
        warnings: list[str] = []
        readiness = self.readiness.payload(date_label=target_date, season=selected_season, market=selected_market)
        market_gate = _first_market(readiness, selected_market)
        if selected_market not in SUPPORTED_BASELINE_MARKETS:
            warnings.append(f"Unsupported baseline market: {selected_market}.")
        if not _xgboost_available():
            warnings.append("xgboost is unavailable; install xgboost to train the baseline model.")

        joined = self._joined_rows(target_date=target_date, season=selected_season, market=selected_market, label_files=readiness.get("labelArtifacts") or [])
        feature_columns = _feature_columns(joined)
        metrics = _empty_metrics(len(joined))
        model_state = "unavailable" if not _xgboost_available() else "research_only"
        artifact_dir = self.artifact_dir(selected_market)
        eligible = bool(market_gate.get("baselineEligible")) and selected_market in SUPPORTED_BASELINE_MARKETS
        if eligible and _xgboost_available():
            model_state = "baseline_ready"
        if not eligible:
            warnings.extend(str(reason) for reason in market_gate.get("reasons") or [])
        if not train:
            return self._payload(
                target_date=target_date,
                mode=mode,
                season=selected_season,
                market=selected_market,
                model_state=model_state,
                dry_run=True,
                training_triggered=False,
                artifact_dir=artifact_dir,
                artifact_written=False,
                metrics=metrics,
                feature_columns=feature_columns,
                readiness=readiness,
                warnings=warnings,
            )
        if not eligible or not _xgboost_available():
            return self._payload(
                target_date=target_date,
                mode=mode,
                season=selected_season,
                market=selected_market,
                model_state=model_state,
                dry_run=False,
                training_triggered=False,
                artifact_dir=artifact_dir,
                artifact_written=False,
                metrics=metrics,
                feature_columns=feature_columns,
                readiness=readiness,
                warnings=warnings,
            )

        trained = _train_xgboost(joined, feature_columns)
        metrics = trained["metrics"]
        metrics["modelState"] = "calibration_needed"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        _write_artifacts(
            artifact_dir=artifact_dir,
            model=trained["model"],
            metrics=metrics,
            feature_columns=feature_columns,
            market=selected_market,
            date_label=target_date,
            season=selected_season,
            readiness=readiness,
        )
        return self._payload(
            target_date=target_date,
            mode=mode,
            season=selected_season,
            market=selected_market,
            model_state="calibration_needed",
            dry_run=False,
            training_triggered=True,
            artifact_dir=artifact_dir,
            artifact_written=True,
            metrics=metrics,
            feature_columns=feature_columns,
            readiness=readiness,
            warnings=warnings,
        )

    def status(self, *, date_label: str | None, season: int | None, market: str) -> dict[str, Any]:
        target_date, _ = resolve_date_mode(date_label)
        selected_season = int(season or self.settings.current_season)
        selected_market = _clean(market)
        readiness = self.readiness.payload(date_label=target_date, season=selected_season, market=selected_market)
        artifact_dir = self.artifact_dir(selected_market)
        metrics_path = artifact_dir / "metrics.json"
        metrics = _read_json(metrics_path)
        artifact_exists = (artifact_dir / "model.joblib").is_file() or (artifact_dir / "model.pkl").is_file()
        model_state = _clean(metrics.get("modelState")) if isinstance(metrics, dict) else ""
        if not model_state:
            model_state = "unavailable" if not _xgboost_available() else ("baseline_ready" if selected_market in readiness.get("eligibleBaselineMarkets", []) else "research_only")
        warnings = list(readiness.get("warnings") or [])
        if not artifact_exists:
            warnings.append("No baseline artifact found for this market.")
        return {
            "schemaVersion": STATUS_SCHEMA_VERSION,
            "date": target_date,
            "season": selected_season,
            "market": selected_market,
            "modelState": model_state if model_state in ALLOWED_MODEL_STATES else "research_only",
            "artifactExists": artifact_exists,
            "metrics": metrics if isinstance(metrics, dict) else {},
            "modelTrainingTriggered": False,
            "externalApiCallsMade": False,
            "readyForProductionTraining": False,
            "warnings": warnings,
        }

    def artifact_dir(self, market: str) -> Path:
        return self.settings.data_dir / "models" / "baseline" / _safe_market(market)

    def _joined_rows(self, *, target_date: str, season: int, market: str, label_files: list[str]) -> list[dict[str, Any]]:
        features = _read_csv(self.settings.data_dir / "features" / f"prop_features_{target_date}.csv")
        labels = []
        for rel in label_files:
            labels.extend(_read_csv(self.settings.root_dir / rel))
        labels.extend(_read_csv(self.settings.data_dir / "labels" / f"player_prop_labels_{season}.csv"))
        labels.extend(_read_csv(self.settings.data_dir / "training" / f"player_prop_labels_{season}.csv"))
        label_index = _LabelJoinIndex.build([row for row in _dedupe_rows(labels) if _clean(row.get("market")) == market and _label_target(row) is not None])
        joined: list[dict[str, Any]] = []
        for feature in features:
            if _clean(feature.get("market")) != market:
                continue
            label = label_index.match(feature)
            target = _label_target(label or {})
            if target is None:
                continue
            joined.append({**feature, "__target": target})
        return joined

    def _payload(
        self,
        *,
        target_date: str,
        mode: str,
        season: int,
        market: str,
        model_state: str,
        dry_run: bool,
        training_triggered: bool,
        artifact_dir: Path,
        artifact_written: bool,
        metrics: dict[str, Any],
        feature_columns: list[str],
        readiness: dict[str, Any],
        warnings: list[str],
    ) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "ok",
            "date": target_date,
            "season": season,
            "resolvedDateMode": mode,
            "market": market,
            "dryRun": dry_run,
            "trainRequested": not dry_run,
            "modelState": model_state,
            "artifactDir": safe_relpath(artifact_dir, self.settings.root_dir),
            "artifactWritten": artifact_written,
            "metrics": metrics,
            "featureColumns": feature_columns,
            "readiness": readiness,
            "modelTrainingTriggered": training_triggered,
            "externalApiCallsMade": False,
            "readyForProductionTraining": False,
            "warnings": _dedupe(warnings),
        }


def _train_xgboost(rows: list[dict[str, Any]], feature_columns: list[str]) -> dict[str, Any]:
    import numpy as np
    from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, precision_score, recall_score, roc_auc_score
    from xgboost import XGBClassifier

    ordered = sorted(rows, key=lambda row: (_clean(row.get("date")), _clean(row.get("player")), _clean(row.get("line"))))
    split_at = max(1, int(len(ordered) * 0.8))
    if split_at >= len(ordered):
        split_at = max(1, len(ordered) - 1)
    train_rows = ordered[:split_at]
    test_rows = ordered[split_at:]
    x_train = np.asarray([[_float(row.get(column)) for column in feature_columns] for row in train_rows], dtype=float)
    y_train = np.asarray([int(row["__target"]) for row in train_rows], dtype=int)
    x_test = np.asarray([[_float(row.get(column)) for column in feature_columns] for row in test_rows], dtype=float)
    y_test = np.asarray([int(row["__target"]) for row in test_rows], dtype=int)
    model = XGBClassifier(n_estimators=40, max_depth=3, learning_rate=0.08, eval_metric="logloss", n_jobs=1, random_state=31)
    model.fit(x_train, y_train)
    probabilities = model.predict_proba(x_test)[:, 1] if len(test_rows) else np.asarray([])
    predictions = (probabilities >= 0.5).astype(int) if len(test_rows) else np.asarray([])
    metrics = {
        "trainRows": len(train_rows),
        "testRows": len(test_rows),
        "positiveRate": float(np.mean([int(row["__target"]) for row in ordered])) if ordered else 0.0,
        "accuracy": _metric(lambda: accuracy_score(y_test, predictions), len(test_rows)),
        "precision": _metric(lambda: precision_score(y_test, predictions, zero_division=0), len(test_rows)),
        "recall": _metric(lambda: recall_score(y_test, predictions, zero_division=0), len(test_rows)),
        "rocAuc": _metric(lambda: roc_auc_score(y_test, probabilities), len(set(y_test.tolist())) > 1),
        "logLoss": _metric(lambda: log_loss(y_test, probabilities, labels=[0, 1]), len(test_rows)),
        "brierScore": _metric(lambda: brier_score_loss(y_test, probabilities), len(test_rows)),
        "modelState": "baseline_trained",
    }
    return {"model": model, "metrics": metrics}


def _write_artifacts(
    *,
    artifact_dir: Path,
    model: Any,
    metrics: dict[str, Any],
    feature_columns: list[str],
    market: str,
    date_label: str,
    season: int,
    readiness: dict[str, Any],
) -> None:
    import joblib

    joblib.dump(model, artifact_dir / "model.joblib")
    (artifact_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=True), encoding="utf-8")
    (artifact_dir / "feature_columns.json").write_text(json.dumps(feature_columns, indent=2, ensure_ascii=True), encoding="utf-8")
    importance = getattr(model, "feature_importances_", [])
    with (artifact_dir / "feature_importance.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["feature", "importance"])
        writer.writeheader()
        for feature, value in zip(feature_columns, importance, strict=False):
            writer.writerow({"feature": feature, "importance": value})
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "trainedAt": datetime.now(timezone.utc).isoformat(),
        "market": market,
        "date": date_label,
        "season": season,
        "modelState": metrics.get("modelState"),
        "readyForProductionTraining": False,
        "readiness": readiness,
    }
    (artifact_dir / "training_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")


def _feature_columns(rows: list[dict[str, Any]]) -> list[str]:
    blocked = set(postgame_label_names()) | IDENTITY_COLUMNS | {"__target"}
    candidates = [column for column in pregame_feature_names() if column not in blocked]
    return [column for column in candidates if any(_clean(row.get(column)) for row in rows) and all(_is_numeric_or_blank(row.get(column)) for row in rows)]


def _label_target(row: dict[str, Any]) -> int | None:
    result = _clean(row.get("result") or row.get("target_result")).lower()
    if result in {"push", "void", "cancelled", "canceled", "ungraded"}:
        return None
    hit = _clean(row.get("hit") if "hit" in row else row.get("target_hit")).lower()
    if hit in {"1", "true", "yes", "hit", "win", "won"} or result in {"hit", "win", "won"}:
        return 1
    if hit in {"0", "false", "no", "miss", "loss", "lost"} or result in {"miss", "loss", "lost"}:
        return 0
    return None


def _empty_metrics(row_count: int) -> dict[str, Any]:
    train_rows, test_rows = _planned_split_counts(row_count)
    return {"trainRows": train_rows, "testRows": test_rows, "positiveRate": None, "modelState": "unavailable", "candidateRows": row_count}


def _first_market(readiness: dict[str, Any], market: str) -> dict[str, Any]:
    for item in readiness.get("markets") or []:
        if _clean(item.get("market")) == market:
            return dict(item)
    return {"market": market, "baselineEligible": False, "reasons": ["No market readiness entry found."]}


IDENTITY_COLUMNS = {
    "date",
    "season",
    "source_row_id",
    "prop_key",
    "game_pk",
    "player_id",
    "playerId",
    "player",
    "team",
    "opponent",
    "market",
    "side",
    "book",
}


class _LabelJoinIndex:
    def __init__(self, *, by_id: dict[str, dict[str, Any]], by_strict: dict[str, dict[str, Any] | None], by_loose: dict[str, dict[str, Any] | None]) -> None:
        self.by_id = by_id
        self.by_strict = by_strict
        self.by_loose = by_loose

    @classmethod
    def build(cls, labels: list[dict[str, Any]]) -> "_LabelJoinIndex":
        by_id: dict[str, dict[str, Any]] = {}
        strict_buckets: dict[str, list[dict[str, Any]]] = {}
        loose_buckets: dict[str, list[dict[str, Any]]] = {}
        for row in labels:
            for key in _identity_keys(row):
                by_id.setdefault(key, row)
            strict = _strict_fallback_key(row)
            if strict:
                strict_buckets.setdefault(strict, []).append(row)
            loose = _loose_fallback_key(row)
            if loose:
                loose_buckets.setdefault(loose, []).append(row)
        return cls(
            by_id=by_id,
            by_strict={key: _unique_row(bucket) for key, bucket in strict_buckets.items()},
            by_loose={key: _unique_row(bucket) for key, bucket in loose_buckets.items()},
        )

    def match(self, feature: dict[str, Any]) -> dict[str, Any] | None:
        for key in _identity_keys(feature):
            if key in self.by_id:
                return self.by_id[key]
        strict = _strict_fallback_key(feature)
        if strict and strict in self.by_strict:
            return self.by_strict[strict]
        loose = _loose_fallback_key(feature)
        if loose and loose in self.by_loose:
            return self.by_loose[loose]
        return None


def _identity_keys(row: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for field in ("prop_key", "propKey", "source_row_id", "sourceRowId"):
        value = _clean(row.get(field))
        if value:
            keys.append(f"id|{value}")
    return _dedupe(keys)


def _strict_fallback_key(row: dict[str, Any]) -> str:
    parts = [
        _clean(row.get("date"))[:10],
        _clean(row.get("market")),
        _norm(row.get("player")),
        _line_key(row.get("line")),
        _norm(row.get("side")),
        _norm(row.get("book")),
    ]
    return "|".join(parts) if all(parts[:4]) and (parts[4] or parts[5]) else ""


def _loose_fallback_key(row: dict[str, Any]) -> str:
    parts = [_clean(row.get("date"))[:10], _clean(row.get("market")), _norm(row.get("player")), _line_key(row.get("line"))]
    return "|".join(parts) if all(parts) else ""


def _unique_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return rows[0] if len(rows) == 1 else None


def _line_key(value: Any) -> str:
    number = _float_or_none(value)
    return f"{number:g}" if number is not None else _clean(value).lower()


def _float_or_none(value: Any) -> float | None:
    try:
        text = _clean(value)
        return float(text) if text else None
    except (TypeError, ValueError):
        return None


def _norm(value: Any) -> str:
    return " ".join(_clean(value).lower().replace(".", "").replace(",", "").split())


def _planned_split_counts(row_count: int) -> tuple[int, int]:
    if row_count <= 0:
        return 0, 0
    split_at = max(1, int(row_count * 0.8))
    if split_at >= row_count:
        split_at = max(1, row_count - 1)
    return split_at, max(0, row_count - split_at)


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except OSError:
        return []


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[tuple[str, str], ...]] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        key = tuple(sorted((str(field), _clean(value)) for field, value in row.items()))
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _metric(callback: Any, available: bool) -> float | None:
    if not available:
        return None
    try:
        return float(callback())
    except Exception:
        return None


def _xgboost_available() -> bool:
    return importlib.util.find_spec("xgboost") is not None


def _is_numeric_or_blank(value: Any) -> bool:
    text = _clean(value)
    if not text:
        return True
    try:
        float(text)
    except (TypeError, ValueError):
        return False
    return True


def _float(value: Any) -> float:
    try:
        text = _clean(value)
        return float(text) if text else 0.0
    except (TypeError, ValueError):
        return 0.0


def _safe_market(value: str) -> str:
    return "".join(char if char.isalnum() or char == "_" else "_" for char in _clean(value)) or "unknown"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
