# Industrial equipment monitoring

This repository implements seven-device industrial monitoring and predictive maintenance: three induction motors, a centrifugal pump, an air compressor, a cooling fan and a generator. The deployment region is Sydney (`ap-southeast-2`), authorized by the user after the account's managed region policy blocked Mumbai. The approved expansion is in `PRD.md`; the completed original requirements are in `PRD.old.md`. Open https://d1idggpc663p7f.cloudfront.net and sign in with an invited team account.

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

The main Markdown handoff is a small set: `PRD.md` for the implemented expansion and `PRD.old.md` for the completed original scope, `PROGRESS.md` for the completed state and next work, and `docs/AWS_ACCEPTANCE.md` for results, measurements and limitations. See `docs/PREDICTIVE_ACCEPTANCE.md` for the expanded implementation and live evidence. This README supplies build/deployment/operation commands. `docs/API.md` and `docs/SHUTDOWN.md` are the focused frontend contract and later cleanup references; `IMPLEMENTATION_PLAN.md` preserves the original phased plan with the updated implementation boundary.

The React application is in `frontend/`: Cognito hosted PKCE login, motor overview/detail/charts, operator controls and acknowledgements, active/historical alerts, asynchronous reports with charts/tables/CSV, and operator user invitations/role assignment. It handles loading, API errors, expired sessions and stale readings. Viewer access is enforced by the existing backend as well as reflected in the UI. The interface uses a compact fixed overview heading, a measurement strip with margin to the temperature limit, live reading ages, per-motor sparklines and threshold gauges. A cool blue measurement color sits alongside orange fault indicators, neutral surfaces and self-hosted IBM Plex fonts. Mobile layouts show every motor metric without sideways table scrolling. Charts support shared hover/keyboard inspection, event markers, visible limits and gaps; detail charts share a time cursor and use stable measurement ranges. Alerts include a 24-hour episode timeline; reset-all requires confirmation. Demo tools remain collapsed. Responsive desktop/mobile layouts, keyboard focus and reduced-motion support are included.

```powershell
Push-Location frontend
npm.cmd ci
npx.cmd playwright install chromium
npm.cmd run build
npm.cmd test
Pop-Location
.venv\Scripts\python.exe -m scripts.publish_frontend frontend/dist
```

Publishing uploads to private S3 and waits for CloudFront invalidation. Keep deployment-owned `config.json` out of the build; infrastructure updates preserve an existing application entry point. Public configuration contains endpoints and IDs only. Tokens exist at runtime in per-tab session storage, never in the build, Git, test evidence or command log; sign-out clears them and requests token revocation and hosted logout. The maintained `oidc-client-ts` library handles OAuth state, PKCE and token renewal. Recharts renders detail/report measurements, while the overview uses a shared SVG comparison with directly labeled motor lines. Charts show threshold lines and gaps for missing samples; after initial pagination, chart polling retrieves new samples with a short overlap rather than rescanning the complete 24-hour window.

## Validation

For initial access, use the temporary password from your Cognito invitation on the normal Sign in screen, then choose your own password. Forgot password requires a verified recovery email. The hosted reset screen can deliberately show simulated delivery details for an account without a verified recovery method; a “code sent” screen alone does not prove that email was sent. Administrators can resend an uncompleted invitation with `admin-create-user --message-action RESEND --desired-delivery-mediums EMAIL` through the command logger; Cognito generates the temporary password. Do not write passwords into source, command arguments or project files.

```powershell
.venv\Scripts\python.exe -m scripts.validate
$env:CCPROJ_LIVE = '1'
.venv\Scripts\python.exe -m pytest -m live -v --junitxml=docs/live-test-results.xml
# UI-only deployed journeys (does not run queue/recovery infrastructure exercises):
.venv\Scripts\python.exe -m pytest tests/live/test_frontend_browser.py -v -s --junitxml=docs/ui-live-acceptance.xml
```

Local tests exercise the full handler pipeline against Moto, partial failures, archive retries, transactional deduplication, older events, fault episodes, controls, user roles, report limits, and safe command logging. Schema checks use cfn-lint; security checks use the version-controlled CloudFormation Guard rules. These are distinct from live AWS tests.

Reports offer Today and Last 7 days presets within the existing query bounds. Recent report references are scoped to the signed-in username in per-tab session storage; reopening a result retrieves its existing report ID without starting a new query. No tokens are stored with report references.

Frontend browser tests use deterministic API fixtures for errors/expiry/permissions/filters/report outcomes and axe accessibility checks. The separate deployed Playwright suite signs in through real Cognito, loads actual charts, triggers and resolves real motor faults/disconnection, renders all three Athena reports, persists disposable-user role changes and signs out. Its pytest launcher supplies temporary credentials in process memory, suppresses invitations for test accounts and deletes those accounts afterward. Browser traces/videos and login screenshots are disabled. Evidence and screenshots are linked in `docs/AWS_ACCEPTANCE.md`.

The live suite creates disposable Cognito test users with invitations suppressed, exercises real token/API authorization, runs EC2 fault/recovery/disconnection controls, briefly pauses the simulator and consumer to test buffering, forces a duplicate outside SQS deduplication, demonstrates DLQ isolation and corrected redrive, checks Athena results/hosting, signs in through hosted OAuth/PKCE, and restores/rebuilds recovery evidence. It restores processing/simulation after exercises and removes disposable test users/recovery tables. Run it during a demonstration maintenance window because all users share the same motors. Test failure requires investigation; tests cannot guarantee every future AWS outage or failure condition.

## Operation and budget

Dashboard views refresh every three seconds, with one-second checks while commands await acknowledgement. All seven assets start normal. Controls poll every five seconds and measurements report every ten seconds. Configurable deterioration profiles default to approximately thirty simulated minutes per cycle, with normal, 5× and 10× speeds. Manual faults remain available. Transient overheating cools/restarts automatically; mechanical faults require operator repair/reset; persistent overheating escalates without repeated restarts. Offline threshold: sixty seconds. Three consecutive breached/healthy readings activate/resolve equipment alerts. Recent readings: 24 hours; archive: 30 days, with bounded noncurrent-version retention. Queries: predefined SQL, at most seven dates and 10 MiB scanned, with 100 starts per UTC day. Logs: seven days. The simulator has no inbound ports, uses IMDSv2, an encrypted 8 GiB disk, standard CPU credits, and role credentials.

The project ceiling is $50 before credits. The expanded seven-device planning estimate is in `docs/predictive-budget-model.json`; inference Lambda alone is estimated at about $1.08 per 730-hour month. This is an estimate, with delayed actual costs tracked by the existing budget. No shutdown date or teardown schedule is configured. Budget email notifications are configured at $20, $30 and $40. The budget conservatively tracks the account during the project period so unactivated cost tags do not silently omit charges; unrelated teammate usage can also trigger it. It does not automatically stop resources. Keep the project online until the user requests shutdown, and ask before stopping anything for spending reasons. Account Free Plan availability and expiry still apply.

SNS email recipient: `collegeproject@akshaykripalani.com`. The recipient must confirm the current live subscription; dashboard/backend alerts work while email is pending. `sns_accepted` means SNS accepted the publication, not that an inbox received it. Equipment emails use a readable Forge subject, the breached value, UTC detection time, supporting measurements and a direct equipment link. Routine Running state, fixed limit/confirmation fields and repeated instructions are omitted; a Stopped state is included when present. They use the recorded activation reading, so the dashboard is the source for current state. See docs/alert-email-example.txt for an illustrative preview. Notification retries can duplicate an email if a worker crashes between publish and recording success; exactly-once delivery is not claimed.

## Recovery and later shutdown

```powershell
.venv\Scripts\python.exe -m scripts.recovery --prefix 'telemetry/day=YYYY-MM-DD/KNOWN_BATCH_ID.json.gz'
```

Recovery creates a separate disposable table, replays a bounded archive prefix preserving event times, and never publishes SNS messages. The output identifies that test stack for subsequent cleanup. Use a known batch or a bounded date partition; the demonstration does not prove Region-wide disaster recovery.

Do not run teardown until the user requests shutdown. Before shutdown, export required telemetry, test evidence, and query results. Then remove the simulator stack, platform stack, and artifact stack, and explicitly handle retained S3 versions/buckets, DynamoDB tables, Cognito pool and encryption key. Stateful resources use `RetainExceptOnCreate`: an unsuccessful initial creation cleans its new resources, while normal stack deletion/replacement retains established data. Deleting a stack alone is not complete cleanup. Disable/delete CloudFront as appropriate, remove retained empty resources only after evidence export, and schedule deletion of the project KMS key with AWS's required waiting period. Verify no project EC2 instance, EBS disk, distribution, retained bucket/table, alarms, schedule, or billable key remains. Detailed identifiers and actual tested cleanup evidence belong in the deployment record and acceptance report.

## Predictive maintenance

A compact random forest predicts overheating or mechanical faults within the next five simulated minutes. It was trained locally in `.venv-ml`, evaluated on independent episodes and exported as portable JSON trees. The inference Lambda needs no scientific Python packages or always-on ML server. `models/README.md` documents the exact inputs, evaluation split, limitations, release selection and rollback commands. The model never receives the hidden failure schedule.

The dashboard preserves the existing Forge visual language, using Healthy / Warning / Fault labels, device-specific measurements, maintenance history and operator-only failure-profile controls. Open Fault simulation to choose a device, enable deterioration, set a cycle length and select a presentation speed. At 10×, five simulated minutes are thirty wall-clock seconds. A mechanical fault shows Repair; persistent overheating also requires manual intervention. Reset-all starts fresh normal cycles while retaining alert/maintenance history.

```powershell
# Reproduce the selected model locally:
.venv-ml\Scripts\python.exe -m scripts.train_model --seed 20261027
# Release backend/model changes without restarting the simulator:
.venv\Scripts\python.exe -m scripts.release_backend
# Select an evaluated prior release to roll back:
.venv\Scripts\python.exe -m scripts.promote_model rf-b8af65a6f20e
```

All operator commands use the audited CLI wrapper, which explicitly pins `default`, rejects `provision`, and removes inherited session credentials. Deploy/release entry points verify account `039379078306` first. The updated report is under `assignment_docs/updated/`, including the visually checked LNCS DOCX/PDF and simple diagram sources. The supplied Downloads report remains untouched.
