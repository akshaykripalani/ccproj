"""Publish a completed React build independently of infrastructure deployment."""

import argparse
import json
from pathlib import Path

from scripts.aws_cli import call, identity, run

ROOT = Path(__file__).resolve().parents[1]


def publish(directory, deployment):
    directory = Path(directory).resolve()
    if not (directory / "index.html").is_file():
        raise ValueError("The frontend build directory must contain index.html")
    if (directory / "config.json").exists():
        raise ValueError("config.json is supplied by AWS deployment; exclude it from the build")
    identity()
    p = deployment["platform"]
    run(
        [
            "s3",
            "sync",
            str(directory),
            "s3://" + p["FrontendBucket"],
            "--cache-control",
            "public,max-age=86400",
            "--sse",
            "AES256",
        ],
        "Publish completed frontend build to the private hosting bucket",
    )
    run(
        [
            "s3",
            "cp",
            str(directory / "index.html"),
            "s3://" + p["FrontendBucket"] + "/index.html",
            "--content-type",
            "text/html",
            "--cache-control",
            "no-cache",
            "--sse",
            "AES256",
        ],
        "Publish frontend entry point with revalidation",
    )
    invalidation = call(
        [
            "cloudfront",
            "create-invalidation",
            "--distribution-id",
            p["DistributionId"],
            "--paths",
            "/*",
        ],
        "Make the explicitly published frontend release visible",
    )["Invalidation"]["Id"]
    run(
        [
            "cloudfront",
            "wait",
            "invalidation-completed",
            "--distribution-id",
            p["DistributionId"],
            "--id",
            invalidation,
        ],
        "Wait for frontend release cache invalidation",
    )
    print(p["DashboardUrl"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("build_directory")
    parser.add_argument("--deployment", default=str(ROOT / ".runtime" / "deployment.json"))
    args = parser.parse_args()
    publish(args.build_directory, json.loads(Path(args.deployment).read_text()))
