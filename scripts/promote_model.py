import argparse
import logging

from ml.registry import ModelRegistry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Promote or rollback a model version")
    parser.add_argument("--version", required=True, help="Version to promote (e.g., v1.0.0)")
    parser.add_argument("--stage", choices=["staging", "production"], default="production",
                        help="Target stage")
    parser.add_argument("--rollback", action="store_true", help="Rollback production to this version")
    parser.add_argument("--list", action="store_true", help="List all registered versions")
    args = parser.parse_args()

    registry = ModelRegistry()

    if args.list:
        versions = registry.list_versions()
        print(f"\nRegistered versions:")
        if not versions:
            print("  (none)")
        for v in versions:
            prod_path = registry.get_production_model()
            staging_path = registry.get_staging_model()
            v_path = f"models/registry/{v['version']}/model.pt"
            stage_info = []
            if prod_path and str(prod_path).endswith(v_path.replace("models/registry/", "")):
                stage_info.append("PRODUCTION")
            if staging_path and str(staging_path).endswith(v_path.replace("models/registry/", "")):
                stage_info.append("STAGING")
            stage_tag = f" [{', '.join(stage_info)}]" if stage_info else ""
            metrics = v.get("metrics", {})
            auc = metrics.get("val_auc_roc", metrics.get("auc", "N/A"))
            print(f"  {v['version']:12s} AUC: {auc}{stage_tag}")
        return

    if args.rollback:
        registry.rollback(args.version)
        print(f"Rolled back production to {args.version}")
        return

    registry.promote(args.version, args.stage)
    print(f"Promoted {args.version} -> {args.stage}")


if __name__ == "__main__":
    main()
