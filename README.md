# Industrial equipment monitoring: AWS layer

This repository implements the PRD's AWS backend and the EC2 three-motor simulator. The deployment region is Sydney (`ap-southeast-2`), authorized by the user after the account's managed region policy blocked Mumbai. The original architecture and product behavior remain unchanged. The React dashboard is the next application stage; its private hosting, Cognito configuration, and application APIs are provided here.

One EC2 gateway sends signed telemetry through API Gateway and an ingestion Lambda to FIFO SQS. A processing Lambda archives batched NDJSON in private S3 and atomically writes current/recent state, event markers, fault history, and notification intent in DynamoDB. EventBridge Scheduler invokes the durable SNS notification worker. Cognito protects dashboard, control, user-management, and bounded Athena report endpoints. Glue supplies a projected archive schema; CloudWatch records logs and operational alarms. CloudFormation owns the infrastructure. No Kinesis, Firehose, or QuickSight is used.

## Deployment

Required account: `039379078306`. Existing CLI authentication must be authorized for Sydney and must permit CloudFormation and scoped role creation/passing. Do not put credentials in this repository. Commands below are invoked from the repository root in PowerShell.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -r requirements-dev.txt
# Install the official CloudFormation Guard binary or set CCPROJ_GUARD to its path.
.venv\Scripts\python.exe -m scripts.deploy
```

Deployment validates the templates and local integration tests, verifies account/service access, builds versioned release packages, provisions the private artifact/platform/simulator stacks, creates the two initial invited users and roles, publishes public non-secret frontend configuration, and supervises the EC2 service. A separate SSM update step applies release changes because EC2 user data does not automatically rerun on later updates.

Use `scripts/aws_cli.py` for any additional operator AWS CLI commands. It appends timestamp, purpose, complete non-secret argument vector, and exit status to `AWS_COMMANDS.txt`. It never copies AWS responses into that record and rejects secret-bearing inline parameters. Live-test authentication inputs use a restrictive operating-system temporary directory outside the repository and are removed after use. Application SDK calls use service roles; they are not operator CLI commands.

```powershell
python scripts/aws_cli.py --purpose 'Inspect platform health' -- cloudformation describe-stacks --stack-name ccproj
```

After deployment, `docs/ccproj-deployment.json` and `.runtime/deployment.json` contain resource identifiers and URLs, with no tokens or credentials. `docs/API.md` gives the frontend integration contract. `PROGRESS.md` records actual verification and pending external actions.

The deployed AWS acceptance report is `docs/AWS_ACCEPTANCE.md`: 64 local tests and 14 distinct real AWS scenarios passed, both fault emails reached the confirmed recipient, and the platform was left online with healthy motors. Raw and consolidated test evidence are under `docs/`.

The main Markdown handoff is a small set: `PRD.md` for scope, `PROGRESS.md` for the completed state and next work, and `docs/AWS_ACCEPTANCE.md` for results, measurements and limitations. This README supplies build/deployment/operation commands. `docs/API.md` and `docs/SHUTDOWN.md` are the focused frontend contract and later cleanup references; `IMPLEMENTATION_PLAN.md` preserves the original phased plan with the updated implementation boundary.

Publish the completed React build separately with `.venv\Scripts\python.exe -m scripts.publish_frontend path\to\dist`. It uploads to private S3 and waits for CloudFront invalidation. Keep deployment-owned `config.json` out of the build; infrastructure updates preserve an existing application entry point. The current entry point is a deployment status page until the React stage is implemented.

## Validation

```powershell
.venv\Scripts\python.exe -m scripts.validate
$env:CCPROJ_LIVE = '1'
.venv\Scripts\python.exe -m pytest -m live -v --junitxml=docs/live-test-results.xml
```

Local tests exercise the full handler pipeline against Moto, partial failures, archive retries, transactional deduplication, older events, fault episodes, controls, user roles, report limits, and safe command logging. Schema checks use cfn-lint; security checks use the version-controlled CloudFormation Guard rules. These are distinct from live AWS tests.

The live suite creates disposable Cognito test users with invitations suppressed, exercises real token/API authorization, runs EC2 fault/recovery/disconnection controls, briefly pauses the simulator and consumer to test buffering, forces a duplicate outside SQS deduplication, demonstrates DLQ isolation and corrected redrive, checks Athena results/hosting, signs in through hosted OAuth/PKCE, and restores/rebuilds recovery evidence. It restores processing/simulation after exercises and removes disposable test users/recovery tables. Run it during a demonstration maintenance window because all users share the same motors. Test failure requires investigation; tests cannot guarantee every future AWS outage or failure condition.

## Operation and budget

All motors start normal. Controls poll every five seconds and measurements report every ten seconds. Faults remain until reset or replaced. Offline threshold: sixty seconds. Three consecutive breached/healthy readings activate/resolve equipment alerts. Recent readings: 24 hours; archive: 30 days, with bounded noncurrent-version retention. Queries: predefined SQL, at most seven dates and 10 MiB scanned, with 100 starts per UTC day. Logs: seven days. The simulator has no inbound ports, uses IMDSv2, an encrypted 8 GiB disk, standard CPU credits, and role credentials.

The project ceiling is $50 before credits. Budget email notifications are configured at $20, $30 and $40. The budget conservatively tracks the account during the project period so unactivated cost tags do not silently omit charges; unrelated teammate usage can also trigger it. It does not automatically stop resources. Keep the project online until the user requests shutdown, and ask before stopping anything for spending reasons. Account Free Plan availability and expiry still apply.

SNS email recipient: `collegeproject@akshaykripalani.com`. The recipient must confirm the current live subscription; dashboard/backend alerts work while email is pending. `sns_accepted` means SNS accepted the publication, not that an inbox received it. Notification retries can duplicate an email if a worker crashes between publish and recording success; exactly-once delivery is not claimed.

## Recovery and later shutdown

```powershell
.venv\Scripts\python.exe -m scripts.recovery --prefix 'telemetry/day=YYYY-MM-DD/KNOWN_BATCH_ID.json.gz'
```

Recovery creates a separate disposable table, replays a bounded archive prefix preserving event times, and never publishes SNS messages. The output identifies that test stack for subsequent cleanup. Use a known batch or a bounded date partition; the demonstration does not prove Region-wide disaster recovery.

Do not run teardown until the user requests shutdown. Before shutdown, export required telemetry, test evidence, and query results. Then remove the simulator stack, platform stack, and artifact stack, and explicitly handle retained S3 versions/buckets, DynamoDB tables, Cognito pool and encryption key. Stateful resources use `RetainExceptOnCreate`: an unsuccessful initial creation cleans its new resources, while normal stack deletion/replacement retains established data. Deleting a stack alone is not complete cleanup. Disable/delete CloudFront as appropriate, remove retained empty resources only after evidence export, and schedule deletion of the project KMS key with AWS's required waiting period. Verify no project EC2 instance, EBS disk, distribution, retained bucket/table, alarms, schedule, or billable key remains. Detailed identifiers and actual tested cleanup evidence belong in the deployment record and acceptance report.
