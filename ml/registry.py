import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

REGISTRY_DIR = Path("models/registry")
STAGING_DIR = Path("models/staging")
PRODUCTION_DIR = Path("models/production")


class ModelRegistry:
    def __init__(self, base_dir: str = "models"):
        self.base_dir = Path(base_dir)
        self.registry_dir = self.base_dir / "registry"
        self.staging_dir = self.base_dir / "staging"
        self.production_dir = self.base_dir / "production"

        for d in [self.registry_dir, self.staging_dir, self.production_dir]:
            os.makedirs(d, exist_ok=True)

    def _next_version(self) -> str:
        existing = [d.name for d in self.registry_dir.iterdir() if d.is_dir() and d.name.startswith("v")]
        versions = []
        for name in existing:
            try:
                parts = name.lstrip("v").split(".")
                versions.append(tuple(int(p) for p in parts))
            except (ValueError, IndexError):
                continue

        if not versions:
            return "v1.0.0"

        latest = max(versions)
        return f"v{latest[0]}.{latest[1] + 1}.0"

    def register(self, model_path: str | Path, metrics: dict | None = None,
                 hyperparameters: dict | None = None, dataset_version: str = "unknown") -> str:
        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        version = self._next_version()
        version_dir = self.registry_dir / version
        os.makedirs(version_dir, exist_ok=True)

        dest = version_dir / "model.pt"
        shutil.copy2(str(model_path), str(dest))

        manifest = {
            "version": version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics or {},
            "hyperparameters": hyperparameters or {},
            "dataset_version": dataset_version,
            "model_filename": "model.pt",
        }

        manifest_path = version_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        self._generate_model_card(version, manifest)

        logger.info(f"Registered model {version} -> {version_dir}")
        return version

    def promote(self, version: str, stage: Literal["staging", "production"]):
        version_dir = self.registry_dir / version
        if not version_dir.exists():
            raise FileNotFoundError(f"Version not found: {version}")

        model_file = version_dir / "model.pt"
        if not model_file.exists():
            raise FileNotFoundError(f"Model file not found for version {version}")

        target_dir = self.staging_dir if stage == "staging" else self.production_dir
        symlink_path = target_dir / "current.pt"

        if symlink_path.exists() or symlink_path.is_symlink():
            symlink_path.unlink()

        rel_path = os.path.relpath(model_file, target_dir)
        symlink_path.symlink_to(rel_path)

        target_manifest = target_dir / "manifest.json"
        manifest_src = version_dir / "manifest.json"
        if manifest_src.exists():
            shutil.copy2(str(manifest_src), str(target_manifest))

        logger.info(f"Promoted {version} -> {stage} ({symlink_path})")

    def get_production_model(self) -> Path | None:
        prod_symlink = self.production_dir / "current.pt"
        if prod_symlink.exists():
            return prod_symlink.resolve()
        staging_symlink = self.staging_dir / "current.pt"
        if staging_symlink.exists():
            return staging_symlink.resolve()
        return None

    def get_staging_model(self) -> Path | None:
        staging_symlink = self.staging_dir / "current.pt"
        if staging_symlink.exists():
            return staging_symlink.resolve()
        return None

    def list_versions(self) -> list[dict]:
        versions = []
        for d in sorted(self.registry_dir.iterdir()):
            if d.is_dir():
                manifest_path = d / "manifest.json"
                if manifest_path.exists():
                    with open(manifest_path) as f:
                        manifest = json.load(f)
                    versions.append(manifest)
        return sorted(versions, key=lambda v: v.get("version", ""), reverse=True)

    def rollback(self, to_version: str):
        version_dir = self.registry_dir / to_version
        if not version_dir.exists():
            raise FileNotFoundError(f"Version not found: {to_version}")

        model_file = version_dir / "model.pt"
        if not model_file.exists():
            raise FileNotFoundError(f"Model file not found for version {to_version}")

        symlink_path = self.production_dir / "current.pt"
        if symlink_path.exists() or symlink_path.is_symlink():
            symlink_path.unlink()

        rel_path = os.path.relpath(model_file, self.production_dir)
        symlink_path.symlink_to(rel_path)

        logger.info(f"Rolled back to {to_version} in production")

    def _generate_model_card(self, version: str, manifest: dict):
        card_path = self.registry_dir / version / "model_card.md"
        metrics = manifest.get("metrics", {})
        hp = manifest.get("hyperparameters", {})

        lines = [
            f"# Model Card: PayShield {version}",
            "",
            f"**Created:** {manifest.get('created_at', 'unknown')}",
            f"**Dataset:** {manifest.get('dataset_version', 'unknown')}",
            "",
            "## Intended Use",
            "Fraud detection for UPI/P2P payment transactions using heterogeneous GNN.",
            "",
            "## Performance Metrics",
            f"- Validation AUC-ROC: {metrics.get('val_auc_roc', 'N/A')}",
            f"- Validation AUC-PR: {metrics.get('val_auc_pr', 'N/A')}",
            f"- Test AUC-ROC: {metrics.get('test_auc_roc', 'N/A')}",
            f"- Test F1: {metrics.get('test_f1', 'N/A')}",
            "",
            "## Hyperparameters",
        ]
        for k, v in hp.items():
            lines.append(f"- {k}: {v}")

        lines.extend([
            "",
            "## Limitations",
            "- Detects structural fraud patterns; may miss sophisticated social engineering",
            "- Performance depends on graph completeness (cold-start problem)",
            "",
            "## Training Data",
            f"Version: {manifest.get('dataset_version', 'unknown')}",
        ])

        with open(card_path, "w") as f:
            f.write("\n".join(lines) + "\n")

        logger.info(f"Model card generated: {card_path}")
