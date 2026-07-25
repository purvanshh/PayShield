import argparse
import json
import logging

from ml.registry import ModelRegistry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Register a trained model")
    parser.add_argument("--model-path", required=True, help="Path to model .pt file")
    parser.add_argument("--metrics", default=None, help="JSON string of metrics")
    parser.add_argument("--metrics-file", default=None, help="Path to JSON metrics file")
    parser.add_argument("--hyperparameters", default=None, help="JSON string of hyperparameters")
    parser.add_argument("--dataset-version", default="unknown", help="Dataset version identifier")
    args = parser.parse_args()

    metrics = {}
    if args.metrics:
        metrics = json.loads(args.metrics)
    elif args.metrics_file:
        with open(args.metrics_file) as f:
            metrics = json.load(f)

    hyperparameters = {}
    if args.hyperparameters:
        hyperparameters = json.loads(args.hyperparameters)

    registry = ModelRegistry()
    version = registry.register(
        model_path=args.model_path,
        metrics=metrics,
        hyperparameters=hyperparameters,
        dataset_version=args.dataset_version,
    )

    print(f"\nModel registered: {version}")
    print(f"  Path: models/registry/{version}/")

    versions = registry.list_versions()
    print(f"\nAll registered versions:")
    for v in versions:
        stage_info = []
        prod_path = registry.get_production_model()
        staging_path = registry.get_staging_model()

        v_path = f"models/registry/{v['version']}/model.pt"
        if prod_path and str(prod_path).endswith(v_path.replace("models/registry/", "")):
            stage_info.append("PRODUCTION")
        if staging_path and str(staging_path).endswith(v_path.replace("models/registry/", "")):
            stage_info.append("STAGING")

        stage_tag = f" [{', '.join(stage_info)}]" if stage_info else ""
        print(f"  {v['version']}{stage_tag}")


if __name__ == "__main__":
    main()
