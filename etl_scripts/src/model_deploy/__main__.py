"""Train a deployment artifact or serve the API and dashboard."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    train = subparsers.add_parser("train")
    train.add_argument("--output-dir", type=Path, required=True)
    train.add_argument("--deployment-config", type=Path)
    train.add_argument("--project-config", type=Path)
    train.add_argument("--training-config", type=Path)
    train.add_argument("--input", type=Path)
    train.add_argument("--device", choices=["cpu"])
    serve = subparsers.add_parser("serve")
    serve.add_argument("--host", default=os.getenv("CDP_BIND_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    args = parser.parse_args(argv)
    if args.command == "train":
        from .services.model_trainer import (
            DEPLOYMENT_CONFIG_PATH,
            train_deployment_artifact,
        )

        manifest = train_deployment_artifact(
            args.output_dir,
            deployment_config_path=args.deployment_config or DEPLOYMENT_CONFIG_PATH,
            project_config_path=args.project_config,
            training_config_path=args.training_config,
            input_path=args.input,
            device=args.device,
        )
        print(json.dumps({
            "model_family": manifest["model_family"],
            "artifact_sha256": manifest["artifact_sha256"],
            "training_fingerprint": manifest["training_fingerprint"],
        }, indent=2))
    else:
        import uvicorn

        uvicorn.run(
            "etl_scripts.src.model_deploy.app:app",
            host=args.host,
            port=args.port,
            proxy_headers=True,
            forwarded_allow_ips="*",
        )


if __name__ == "__main__":
    main()
