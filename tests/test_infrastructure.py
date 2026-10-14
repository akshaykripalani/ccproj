import json
from pathlib import Path

import pytest

from infra.generate import build

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def templates():
    build()
    return {name: json.loads((ROOT / "infra" / f"{name}.json").read_text()) for name in ("bootstrap", "platform", "simulator")}


def test_all_buckets_private_encrypted_versioned_and_retention_bounded(templates):
    for template in templates.values():
        for resource in template["Resources"].values():
            if resource["Type"] == "AWS::S3::Bucket":
                props = resource["Properties"]
                assert all(props["PublicAccessBlockConfiguration"].values())
                assert props["BucketEncryption"]
                assert props["VersioningConfiguration"]["Status"] == "Enabled"
                rule = props["LifecycleConfiguration"]["Rules"][0]
                assert rule["ExpirationInDays"] == rule["NoncurrentVersionExpiration"]["NoncurrentDays"]
                assert resource["DeletionPolicy"] == "Retain"


def test_every_route_is_protected_and_client_has_no_secret(templates):
    resources = templates["platform"]["Resources"]
    routes = [r["Properties"] for r in resources.values() if r["Type"] == "AWS::ApiGatewayV2::Route"]
    assert len(routes) == 12
    assert all(route["AuthorizationType"] in ("JWT", "AWS_IAM") for route in routes)
    assert resources["TelemetryRoute"]["Properties"]["AuthorizationType"] == "AWS_IAM"
    browser = resources["BrowserClient"]["Properties"]
    assert browser["GenerateSecret"] is False and browser["AllowedOAuthFlows"] == ["code"]
    assert resources["Pool"]["Properties"]["AdminCreateUserConfig"]["AllowAdminCreateUserOnly"]


def test_queue_retry_and_processor_partial_failure_configuration(templates):
    resources = templates["platform"]["Resources"]
    queue = resources["Telemetry"]["Properties"]
    assert queue["FifoQueue"] and queue["SqsManagedSseEnabled"]
    assert queue["VisibilityTimeout"] >= 6 * resources["Processor"]["Properties"]["Timeout"]
    assert resources["ProcessingMapping"]["Properties"]["FunctionResponseTypes"] == ["ReportBatchItemFailures"]


def test_ec2_has_no_inbound_ports_no_nat_and_requires_imdsv2(templates):
    resources = templates["simulator"]["Resources"]
    assert not resources["SecurityGroup"]["Properties"].get("SecurityGroupIngress")
    assert not any(r["Type"] == "AWS::EC2::NatGateway" for r in resources.values())
    props = resources["Instance"]["Properties"]
    assert props["MetadataOptions"]["HttpTokens"] == "required"
    assert props["BlockDeviceMappings"][0]["Ebs"]["Encrypted"]
    assert props["CreditSpecification"]["CPUCredits"] == "standard"


def test_budget_notification_amounts_and_no_automated_shutdown(templates):
    resources = templates["platform"]["Resources"]
    budget = resources["ProjectBudget"]["Properties"]
    assert [n["Notification"]["Threshold"] for n in budget["NotificationsWithSubscribers"]] == [20, 30, 40]
    assert budget["Budget"]["CostTypes"]["IncludeCredit"] is False
    assert not any(r["Type"] == "AWS::Budgets::BudgetsAction" for r in resources.values())


def test_query_scan_and_log_retention_limits(templates):
    resources = templates["platform"]["Resources"]
    assert resources["Workgroup"]["Properties"]["WorkGroupConfiguration"]["BytesScannedCutoffPerQuery"] == 10485760
    assert all(r["Properties"]["RetentionInDays"] <= 7 for r in resources.values() if r["Type"] == "AWS::Logs::LogGroup")
