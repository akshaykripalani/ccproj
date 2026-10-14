"""Capture public Sydney price evidence and calculate a conservative workload model."""

import concurrent.futures
import datetime as dt
import json
from pathlib import Path

from scripts.aws_cli import call

ROOT = Path(__file__).resolve().parents[1]


def pricing(service):
    result = call(
        [
            "pricing",
            "get-products",
            "--region",
            "us-east-1",
            "--service-code",
            service,
            "--filters",
            "Type=TERM_MATCH,Field=location,Value=Asia Pacific (Sydney)",
        ],
        "Capture current Sydney pricing: " + service,
    )
    dimensions = []
    for value in result["PriceList"]:
        product = json.loads(value)
        for term in product["terms"].get("OnDemand", {}).values():
            for dimension in term["priceDimensions"].values():
                dimensions.append(
                    {
                        "sku": product["product"]["sku"],
                        "attributes": product["product"]["attributes"],
                        "description": dimension["description"],
                        "unit": dimension["unit"],
                        "usd": dimension["pricePerUnit"].get("USD"),
                        "beginRange": dimension["beginRange"],
                        "effectiveDate": term["effectiveDate"],
                    }
                )
    return {"service": service, "dimensions": dimensions}


def main():
    services = [
        "AmazonDynamoDB",
        "AWSQueueService",
        "AmazonSNS",
        "AmazonVPC",
        "AWSLambda",
        "awskms",
        "AmazonCloudWatch",
        "AmazonS3",
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        snapshot = list(executor.map(pricing, services))
    destination = ROOT / "docs" / "pricing-snapshot.json"
    destination.write_text(
        json.dumps(
            {
                "checkedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
                "region": "ap-southeast-2",
                "source": "AWS Price List API; public on-demand rates before credits",
                "prices": snapshot,
            },
            indent=2,
        )
        + "\n"
    )
    for service in snapshot:
        print(service["service"], len(service["dimensions"]), "price dimensions recorded")


if __name__ == "__main__":
    main()
