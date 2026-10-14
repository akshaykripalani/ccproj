import concurrent.futures
import subprocess
from unittest.mock import patch

import pytest

from scripts import aws_cli


def test_command_log_appends_before_execution_and_never_copies_private_responses(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(aws_cli, "ROOT", tmp_path)
    record = tmp_path / "AWS_COMMANDS.txt"
    record.write_text("previous commands\n")

    def execute(args, **kwargs):
        assert "COMMAND argv" in record.read_text()
        assert "ap-south-1" in args
        return subprocess.CompletedProcess(args, 0, '{"token":"sensitive-response"}', "")

    with patch.object(aws_cli.subprocess, "run", side_effect=execute):
        result = aws_cli.run(["sts", "get-caller-identity"], "test audit", private=True)
    assert "sensitive-response" in result.stdout
    assert record.read_text().startswith("previous commands\n")
    assert "sensitive-response" not in record.read_text()
    assert "EXIT 0" in record.read_text()


@pytest.mark.parametrize(
    "arguments",
    [
        ["cognito-idp", "admin-set-user-password", "--password", "hidden"],
        ["cognito-idp", "admin-set-user-password", "--password=hidden"],
        ["cognito-idp", "admin-initiate-auth", "--auth-parameters", "PASSWORD=hidden"],
        ["cognito-idp", "admin-initiate-auth", "--cli-input-json", '{"Password":"hidden"}'],
    ],
)
def test_secret_bearing_arguments_are_rejected_without_logging(tmp_path, monkeypatch, arguments):
    monkeypatch.setattr(aws_cli, "ROOT", tmp_path)
    with patch.object(aws_cli.subprocess, "run") as execute:
        with pytest.raises(ValueError):
            aws_cli.run(arguments, "must not expose secrets")
        execute.assert_not_called()
    assert not (tmp_path / "AWS_COMMANDS.txt").exists()


def test_concurrent_log_writers_preserve_all_commands_and_outcomes(tmp_path, monkeypatch):
    monkeypatch.setattr(aws_cli, "ROOT", tmp_path)

    def execute(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, "{}", "")

    with patch.object(aws_cli.subprocess, "run", side_effect=execute):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(
                pool.map(lambda i: aws_cli.run(["s3api", "list-buckets"], f"check-{i}"), range(20))
            )
    text = (tmp_path / "AWS_COMMANDS.txt").read_text()
    assert text.count("COMMAND argv:") == 20 and text.count("EXIT 0") == 20
