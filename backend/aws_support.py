"""Reusable clients with bounded retries; AWS roles supply all credentials."""
import json
import os
from functools import lru_cache

import boto3
from botocore.config import Config

from backend.domain import canonical

CONFIG = Config(retries={"mode": "standard", "total_max_attempts": 3}, connect_timeout=3, read_timeout=10)


@lru_cache
def client(service):
    return boto3.client(service, config=CONFIG)


@lru_cache
def dynamodb():
    return boto3.resource("dynamodb", config=CONFIG)


def table(variable="DATA_TABLE"):
    return dynamodb().Table(os.environ[variable])


def response(code, body):
    return {"statusCode": code, "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"}, "body": canonical(body)}


def body(event):
    import base64
    value = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        value = base64.b64decode(value).decode()
    if len(value.encode()) > 65536:
        raise ValueError("Request body is too large")
    return json.loads(value)


def get_item(target, pk, sk):
    return target.get_item(Key={"pk": pk, "sk": sk}, ConsistentRead=True).get("Item")


def query_items(target, condition, **kwargs):
    # Resource client paginators retain native type serialization.
    return [item for page in target.meta.client.get_paginator("query").paginate(
        TableName=target.name, KeyConditionExpression=condition, **kwargs
    ) for item in page["Items"]]
