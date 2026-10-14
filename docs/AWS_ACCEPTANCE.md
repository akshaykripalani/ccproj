# Deployed AWS acceptance — 14 October 2026

The complete AWS layer of the PRD is deployed and operating in account **039379078306**, **Sydney (`ap-southeast-2`)**, on the existing Free Plan. The user authorized Sydney after the managed account policy blocked Mumbai. Three CloudFormation stacks own the platform, artifact storage and EC2 simulator. The React dashboard remains the subsequent application stage; the live hosting entry point currently shows deployment status.

- Hosting: https://d1idggpc663p7f.cloudfront.net
- Protected API: https://9ojy2mmg65.execute-api.ap-southeast-2.amazonaws.com
- Hosted login: https://ccproj-039379078306.auth.ap-southeast-2.amazoncognito.com
- Simulator: i-098cf45e426dd3ab7; one gateway, three shared motors.

## Verification results

**64 local tests passed**, alongside cfn-lint, CloudFormation Guard for all three templates, and Ruff across the source/test directories. **14 distinct real AWS E2E scenarios passed across several runs.** `live-acceptance.json` and `live-acceptance.xml` consolidate the latest result per scenario. Original run XML files are retained, including earlier failed test assertions and their subsequent passing reruns.

| Verified behavior | Evidence |
| --- | --- |
| Healthy EC2 operation and actual fault ramps | Real motor-01 overheat and vibration activation/resolution; motor-02 unaffected; reset all |
| Individual outage/reset and acknowledgements | Real disconnect, offline detection, remote reset, pending/applied request IDs |
| Authentication | Real Cognito tokens and hosted OAuth authorization-code/PKCE exchange; direct unauthenticated/ID-token ingestion/read requests rejected |
| User management | Both specified initial users have viewer/operator roles; API creates a disposable user, changes roles, rejects viewers and rejects stale operator privilege after removal |
| Pipeline ordering and duplicate handling | Signed API ingestion, DynamoDB state/recent records, older-event preservation, duplicate forced beyond SQS deduplication |
| Buffering and catch-up | Consumer disabled, ingestion still accepts/queues, consumer enabled, reading appears afterward |
| Failure isolation and recovery | Real invalid queue envelope retries into DLQ; inspected invalid body removed, corrected envelope redriven successfully |
| Input and load | Signed malformed input rejected with 400; bounded 24-reading burst processed; reporting stopped motor remains online with zero power |
| Equipment email | Current subscription confirmed in AWS; overheat/vibration intents have SNS message IDs; **user confirmed both emails arrived**; repeated notifier publishes zero completed episodes |
| Historical reports | All three predefined reports complete; results owner protected; 10 MiB scan bound; known inserted readings cross-check temperature average/max/count, vibration breaches and running-power average/count |
| Private hosting/cache | CloudFront HTTPS/config/headers work; direct private S3 reads rejected; cache hit demonstrated, origin updated, explicit invalidation exposes new content |
| Limited recovery | Versioned test object restored after overwrite/delete; isolated three-device state table rebuilt from archive preserving event times; temporary recovery stack deleted |

Measured signed-ingestion-to-current-state latency was **5.063 seconds**, including API polling, below the 30-second normal-load target. Object restore plus separate-table creation/reconstruction took **70.641 seconds** before verification and cleanup; the whole recovery test took 137.105 seconds. This recovers a known three-reading batch, not an entire Region or full production dataset.

## Final deployed health

`deployed-evidence.json` captures the final state: all three motors report running with healthy fault rules, the consumer is Enabled, telemetry queue and DLQ counts are zero at capture, the EC2 managed node is Online, and all ten operational alarms are OK. Telemetry continues every ten seconds. The snapshot also records private hosting, enabled DynamoDB TTL, S3 versioning/retention, Athena scan enforcement, budget notifications and the confirmed SNS subscription. Three intentional poison-message failures are preserved from CloudWatch logs.

Fault notification IDs are retained in `notification-evidence.json`. Inbox receipt was reported directly by the user after these SNS acceptance records were verified. Standard SNS/worker retry behavior is at least once: a crash between publication and recording success can duplicate mail; exactly-once delivery is not promised.

## Budget and continued operation

The ceiling remains **$50 service usage before credits**. Actual-cost email thresholds of **$20/$30/$40** were verified through AWS Budgets. The account-wide budget covers the project period and excludes credit/refund offsets; unrelated teammate spending can trigger it. Budget alerts do not stop resources. Ask the user before stopping anything for spending reasons, and keep the deployment online until shutdown is requested.

The conservative captured Sydney rate model is **$26.93 per 730-hour month**, including a $5 variable-services allowance, before credits/free allowances. It is an estimate, not indefinite operation within $50. AWS's budget snapshot currently reports $0, but billing data is delayed, so this does not prove that incurred cost is zero. The existing Free Plan expires on 16 March 2027; no upgrade was made.

## Resolved issues and practical limits

The first platform creation rolled back because SQS requires a separate statement/resource policy per queue. This was fixed, and its empty retained resources were inspected and cleaned. An EC2 release race was fixed by waiting for cloud-init before updating the service. Recovery tests were corrected to inspect S3 `Contents` because the CLI's paginated output omits `KeyCount`. The buffering test now lets an existing long poll finish after mapping disable; CloudWatch showed that poll consuming an immediately injected message despite the mapping reporting Disabled.

Tests cover the defined AWS scenarios and do not guarantee every future outage, IAM change, concurrency pattern or external delivery condition. The single EC2 gateway is an intentional demonstration dependency. Full live teardown was not run because the user requires continued operation; `SHUTDOWN.md` gives ordered future cleanup instructions and retained identifiers. The cleanup of failed initial creation resources and disposable recovery stacks was actually exercised.

## Frontend handoff

Use `API.md` and CloudFront `/config.json` for the React implementation. Cognito invitations for both initial accounts have been created; the frontend needs hosted login/callback/sign-out handling, shared motor views/charts/controls, user management and report visualization. The underlying APIs are live and tested. Publish a completed React build with `scripts.publish_frontend`; later infrastructure updates preserve its entry point. Do not place secrets in the build.

All operator AWS CLI commands, including failures, are appended to `AWS_COMMANDS.txt` with timestamps, purpose and exit status. Commands are executed through `scripts.aws_cli`; responses and sensitive authentication inputs are withheld. Source and evidence were committed in incremental milestones.
