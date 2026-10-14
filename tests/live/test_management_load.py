import datetime as dt
import json
import secrets

import pytest

from backend.domain import timestamp, utcnow
from scripts.aws_cli import call
from tests.live.conftest import PROJECT, wait_for
from tests.live.test_aws_e2e import measurement

pytestmark = pytest.mark.live


def test_confirmed_fault_notification_acceptance_and_retry_suppression(live):
    confirmed = call(
        ["sns", "list-subscriptions-by-topic", "--topic-arn", live.platform["AlertTopicArn"]],
        "Verify confirmed fault-notification recipient",
    )["Subscriptions"]
    assert any(
        s["Endpoint"] == "collegeproject@akshaykripalani.com"
        and s["SubscriptionArn"] != "PendingConfirmation"
        for s in confirmed
    )
    intents = call(
        [
            "dynamodb",
            "query",
            "--table-name",
            live.platform["DataTable"],
            "--consistent-read",
            "--key-condition-expression",
            "pk = :p",
            "--expression-attribute-values",
            json.dumps({":p": {"S": "NOTIFY"}}),
        ],
        "Verify real fault episodes were accepted by SNS",
    )["Items"]
    assert {
        i["rule"]["S"]
        for i in intents
        if i["delivery"]["S"] == "sns_accepted" and i.get("snsMessageId")
    } >= {"temperature", "vibration"}
    response = PROJECT / ".runtime" / "notification-retry-test.json"
    result = call(
        [
            "lambda",
            "invoke",
            "--function-name",
            live.platform["NotifierFunction"],
            "--cli-binary-format",
            "raw-in-base64-out",
            "--payload",
            "{}",
            str(response),
        ],
        "Verify notification retry does not republish completed episodes",
    )
    assert "FunctionError" not in result
    assert json.loads(response.read_text())["published"] == 0


def test_initial_accounts_and_operator_user_management(live):
    listed = live.api("GET", "/users")
    assert listed.status_code == 200
    required = {"akshay.kripalani74@nmims.in", "collegeproject@akshaykripalani.com"}
    found = {}
    for user in listed.json()["users"]:
        email = next((a["Value"] for a in user["attributes"] if a["Name"] == "email"), None)
        if email in required:
            found[email] = set(user["roles"])
    assert set(found) == required and all(
        roles == {"viewer", "operator"} for roles in found.values()
    )
    email = "ccproj-api-management-" + secrets.token_hex(8) + "@example.invalid"
    viewer = live.users["viewer"][0]
    try:
        created = live.api("POST", "/users", {"email": email, "roles": ["viewer"]})
        assert created.status_code == 201
        assert (
            live.api("PUT", "/users", {"email": email, "roles": ["viewer", "operator"]}).status_code
            == 200
        )
        current = live.api("GET", "/users").json()["users"]
        added = next(
            u
            for u in current
            if any(a["Name"] == "email" and a["Value"] == email for a in u["attributes"])
        )
        assert set(added["roles"]) == {"viewer", "operator"}
        assert (
            live.api(
                "POST", "/users", {"email": email, "roles": ["viewer"]}, role="viewer"
            ).status_code
            == 403
        )
        assert (
            live.api(
                "PUT", "/users", {"email": viewer, "roles": ["viewer", "operator"]}
            ).status_code
            == 200
        )
        live.tokens.pop("viewer", None)
        assert live.api("GET", "/users", role="viewer").status_code == 200
        assert live.api("PUT", "/users", {"email": viewer, "roles": ["viewer"]}).status_code == 200
        # Retain the access token carrying its old operator group; directory checks
        # must deny it immediately after removal of the actual operator role.
        assert live.api("GET", "/users", role="viewer").status_code == 403
    finally:
        live.api("PUT", "/users", {"email": viewer, "roles": ["viewer"]})
        live.tokens.pop("viewer", None)
        call(
            [
                "cognito-idp",
                "admin-delete-user",
                "--user-pool-id",
                live.platform["UserPoolId"],
                "--username",
                email,
            ],
            "Remove only API-created disposable management test account",
            check=False,
        )


def test_bounded_burst_and_reporting_stopped_motor(paused_simulator):
    live = paused_simulator
    observed = utcnow() - dt.timedelta(seconds=15)
    readings = []
    for index in range(8):
        batch = [
            measurement(
                device=f"motor-0{i}", observed=timestamp(observed + dt.timedelta(seconds=index))
            )
            for i in range(1, 4)
        ]
        batch[0].update(operatingState="stopped", powerWatts=0)
        assert live.send(batch)[0] == 202
        readings.extend(batch)
    expected = {r["eventId"] for r in readings}

    def caught_up():
        actual = {
            r["eventId"]
            for i in range(1, 4)
            for r in live.api("GET", f"/devices/motor-0{i}/readings").json()["readings"]
        }
        return expected.issubset(actual)

    wait_for(caught_up, timeout=90)
    state = live.state("motor-01")
    assert state["online"] and state["latest"]["operatingState"] == "stopped"
    assert state["latest"]["powerWatts"] == 0
    assert not any(rule["active"] for rule in state["latest"]["rules"].values())
    counts = call(
        [
            "sqs",
            "get-queue-attributes",
            "--queue-url",
            live.platform["QueueUrl"],
            "--attribute-names",
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
        ],
        "Verify bounded burst consumer catch-up",
    )["Attributes"]
    assert sum(map(int, counts.values())) == 0
