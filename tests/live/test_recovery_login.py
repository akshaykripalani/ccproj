import base64
import datetime as dt
import hashlib
import json
import secrets
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import pytest
import requests

from backend.domain import digest, timestamp, utcnow
from scripts.aws_cli import call, run
from scripts.recovery import recover
from tests.live.conftest import PROJECT, wait_for
from tests.live.test_aws_e2e import measurement

pytestmark = pytest.mark.live


class LoginForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = {}
        self.action = None

    def handle_starttag(self, tag, attributes):
        values = dict(attributes)
        if tag == "form" and values.get("method", "").lower() == "post":
            self.action = values.get("action")
        if tag == "input" and values.get("type") == "hidden" and values.get("name"):
            self.hidden[values["name"]] = values.get("value", "")


def test_real_hosted_login_authorization_code_pkce(live):
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    state = secrets.token_hex(16)
    callback = live.platform["DashboardUrl"] + "/callback"
    parameters = {
        "response_type": "code",
        "client_id": live.platform["ClientId"],
        "redirect_uri": callback,
        "scope": "openid email profile",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    session = requests.Session()
    try:
        page = session.get(
            live.platform["LoginDomain"] + "/oauth2/authorize?" + urlencode(parameters), timeout=20
        )
        assert page.status_code == 200
        form = LoginForm()
        form.feed(page.text)
        assert form.action and form.hidden, "Hosted login form and CSRF fields were not found"
        target = urljoin(page.url, form.action)
        assert urlparse(target).hostname == urlparse(live.platform["LoginDomain"]).hostname
        email, password = live.users["operator"]
        signed_in = session.post(
            target,
            data={
                **form.hidden,
                "username": email,
                "password": password,
                "signInSubmitButton": "Sign in",
            },
            allow_redirects=False,
            timeout=20,
        )
        assert signed_in.status_code in (302, 303), (
            "Hosted login did not produce an authorization redirect"
        )
        redirected = urlparse(signed_in.headers["Location"])
        assert redirected.hostname == urlparse(callback).hostname
        values = parse_qs(redirected.query)
        assert values.get("state") == [state] and "code" in values
        tokens = session.post(
            live.platform["LoginDomain"] + "/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "client_id": live.platform["ClientId"],
                "redirect_uri": callback,
                "code": values["code"][0],
                "code_verifier": verifier,
            },
            timeout=20,
        )
        assert tokens.status_code == 200
        authorized = session.get(
            live.platform["ApiUrl"] + "/devices",
            headers={"Authorization": "Bearer " + tokens.json()["access_token"]},
            timeout=20,
        )
        assert authorized.status_code == 200
    finally:
        session.close()


def test_real_version_restore_and_separate_state_reconstruction(paused_simulator):
    live = paused_simulator
    bucket = live.platform["ArchiveBucket"]
    unique = secrets.token_hex(8)
    key = "recovery/e2e-" + unique + ".txt"
    location = PROJECT / ".runtime" / ("recovery-proof-" + unique + ".txt")
    location.write_text("original recovery evidence")
    original = call(
        ["s3api", "put-object", "--bucket", bucket, "--key", key, "--body", str(location)],
        "Live E2E: store owned version-recovery test object",
    )["VersionId"]
    location.write_text("overwritten recovery evidence")
    call(
        ["s3api", "put-object", "--bucket", bucket, "--key", key, "--body", str(location)],
        "Live E2E: overwrite owned version test object",
    )
    call(
        ["s3api", "delete-object", "--bucket", bucket, "--key", key],
        "Live E2E: create a delete marker on owned test object",
    )
    call(
        [
            "s3api",
            "copy-object",
            "--bucket",
            bucket,
            "--key",
            key,
            "--copy-source",
            bucket + "/" + key + "?versionId=" + original,
        ],
        "Live E2E: restore original test object version",
    )
    run(
        ["s3api", "get-object", "--bucket", bucket, "--key", key, str(location)],
        "Read restored test object",
    )
    assert location.read_text() == "original recovery evidence"
    observed = timestamp(utcnow() - dt.timedelta(hours=23))
    readings = [
        measurement(device=f"motor-0{i}", observed=observed, temperature=50 + i)
        for i in range(1, 4)
    ]
    assert live.send(readings)[0] == 202
    archive_key = f"telemetry/day={observed[:10]}/{digest(readings)}.json.gz"
    wait_for(
        lambda: (
            call(
                ["s3api", "list-objects-v2", "--bucket", bucket, "--prefix", archive_key],
                "Wait for owned recovery telemetry archive",
            ).get("KeyCount", 0)
            == 1
        )
    )
    recovered = recover(live.deployment, archive_key)
    try:
        assert recovered["devices"] == 3 and recovered["uniqueEvents"] == 3
        assert recovered["table"] != live.platform["DataTable"]
        for reading in readings:
            result = call(
                [
                    "dynamodb",
                    "get-item",
                    "--table-name",
                    recovered["table"],
                    "--key",
                    json.dumps({"pk": {"S": reading["deviceId"]}, "sk": {"S": "STATE"}}),
                ],
                "Verify rebuilt isolated device state",
            )
            assert result["Item"]["observedAt"]["S"] == observed
            assert result["Item"]["eventId"]["S"] == reading["eventId"]
    finally:
        run(
            ["cloudformation", "delete-stack", "--stack-name", recovered["stack"]],
            "Remove only the disposable recovery exercise stack",
        )
        run(
            ["cloudformation", "wait", "stack-delete-complete", "--stack-name", recovered["stack"]],
            "Wait for disposable recovery table cleanup",
        )
