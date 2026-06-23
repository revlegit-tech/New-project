from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.config import Settings
from mlb_app.services.model_training_service import ModelTrainingService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Train offline MLB prop model candidates from Sprint 18 feature_/target_/meta_ datasets."
    )
    parser.add_argument("--training-path", required=True, help="CSV or JSON training dataset built by scripts/build_ml_training_dataset.py.")
    parser.add_argument("--markets", nargs="*", default=None, help="Market keys to train. Defaults to markets present in the dataset.")
    parser.add_argument("--models", nargs="*", default=None, help="Trainer keys to run instead of the Sprint 17 market candidates.")
    parser.add_argument("--status", choices=["candidate", "shadow"], default="candidate")
    parser.add_argument("--model-version", default="", help="Optional immutable model version label.")
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--model-dir", default=str(ROOT / "data" / "models"))
    parser.add_argument("--registry", default="", help="Registry JSON path. Defaults to <model-dir>/model_registry.json.")
    parser.add_argument("--artifact-root", default="", help="Artifact output root. Defaults to <model-dir>/artifacts/sprint19.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test-mode", action="store_true", help="Lower row thresholds and estimator sizes for deterministic fixtures.")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir).resolve()
    model_dir = Path(args.model_dir).resolve()
    registry = Path(args.registry).resolve() if args.registry else model_dir / "model_registry.json"
    settings = Settings(
        root_dir=ROOT,
        public_dir=ROOT / "public",
        data_dir=data_dir,
        model_dir=model_dir,
        model_registry_path=registry,
    )
    service = ModelTrainingService(settings=settings)
    if args.artifact_root:
        from mlb_app.ml.registry.artifact_writer import ModelArtifactWriter

        service = ModelTrainingService(settings=settings, artifact_writer=ModelArtifactWriter(Path(args.artifact_root).resolve()))

    result = service.train_from_dataset(
        training_path=Path(args.training_path).resolve(),
        markets=args.markets,
        model_keys=args.models,
        model_version=args.model_version or None,
        registry_status=args.status,
        registry_path=registry,
        dry_run=args.dry_run,
        test_mode=args.test_mode,
    )
    print(json.dumps(result.as_dict(), indent=2, default=str))
    return 0 if result.status in {"trained", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
