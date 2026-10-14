# Deployed AWS acceptance — 14 October 2026

The complete AWS layer of the PRD is deployed and operating in account **039379078306**, **Sydney (`ap-southeast-2`)**, on the existing Free Plan. The user authorized Sydney after the managed account policy blocked Mumbai. Three CloudFormation stacks own the platform, artifact storage and EC2 simulator. The subsequently requested React dashboard is now deployed at the same CloudFront entry point; UI acceptance is recorded below.

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

## React dashboard and browser acceptance

The React application in `frontend/` replaces the original hosting placeholder. It implements hosted Cognito authorization-code/PKCE login/callback/logout, token renewal/expiry, role-aware navigation, three shared motors with current measurements/freshness, recent temperature/vibration/power charts, independent operator fault/reset controls with requested/applied acknowledgement, alert history/filtering/notification state, asynchronous historical reports and CSV exports, and operator user invitations/role assignment. The original feature scope remains unchanged. README.md has build/publish/test commands; API.md remains the backend contract.

**22 controlled Playwright browser scenarios passed.** These exercise normal/offline/stopped/pending/failed control states, viewer restrictions, 24-hour pagination, alert filters/email status, all three report kinds and CSV exports, report validation/empty/failure states, invitations/roles/self-role protection, API failure/retry, OAuth PKCE/state rejection, expiry/renewal/logout, stale telemetry, mobile navigation/no overflow, and axe WCAG 2 A/AA checks on overview, report form/results, alert history and team management. Deterministic fixtures make rare errors reproducible; they are separate from real AWS proof.

**Four real deployed browser scenarios passed** (`ui-live-acceptance.xml`, 275.73 seconds including account setup/cleanup):

| Browser journey | Verified result |
| --- | --- |
| Real hosted PKCE login and live equipment | Operator desktop and viewer mobile sign in through Cognito; callback removes the code; actual recent charts/pagination render; no page errors or CSP violations; viewer controls/user management unavailable |
| Motor controls and recovery | Overheat on motor-01 and vibration on motor-02 receive simulator acknowledgements and produce visible stored alerts; other motors remain healthy; reset resolves both faults; disconnect becomes offline; final reset restores all three motors healthy |
| Historical reports | Temperature, vibration and running-power queries complete through deployed Athena; result charts/tables display real motor rows; all three CSV downloads work |
| Team management and logout | Both initial accounts appear; a disposable viewer gains an operator role through the browser, survives reload, then loses that role; hosted sign-out returns to the login page |

The initial browser run was interrupted after its selector chose Cognito's hidden desktop/mobile duplicate form. `ui-live-interrupted.xml` preserves that failure. The selector now chooses visible fields, and the full rerun passed. Test credentials remain only in an OS-protected temporary input directory/process memory/browser runtime; invitations for test accounts are suppressed, accounts are deleted, and traces/videos/login screenshots are disabled.

The only infrastructure update for the UI was the existing CloudFront security-header resource, verified by comparing the deployed template. Recharts needs inline style **attributes** for responsive layout; external/inline scripts and external style elements remain blocked. cfn-lint, Guard and all 64 existing non-live backend/infrastructure tests passed. Production builds pass strict TypeScript checking, contain no configuration/secrets, and split application/vendor/chart bundles. Every AWS publishing/invalidation operation goes through the append-only command logger. Subsequent infrastructure deployments preserve the React entry point.

After final contrast/freshness polish, the published build passed another real desktop/mobile Cognito/login/chart smoke (`ui-live-smoke.xml/json`). `ui-acceptance.json` records all 22 controlled scenarios and release SHA-256 hashes; every public asset was fetched and matched against that build. The platform stack is UPDATE_COMPLETE, no disposable test accounts remain, and npm audit reports zero known vulnerabilities. Automated accessibility checks cover the tested views and do not replace a full manual accessibility audit.

Screenshots captured from the real deployment: [desktop overview](ui-overview-desktop.png), [motor detail/charts](ui-device-desktop.png), [active/resolved alerts](ui-alerts-desktop.png), [report results](ui-reports-desktop.png), and [mobile viewer overview](ui-overview-mobile.png). They contain real archived history, including earlier test readings, rather than fabricated production telemetry. The test users visible in screenshots are disposable accounts.

Browser tests verify these journeys; they cannot guarantee future AWS availability or inbox delivery. The invitation UI was tested with controlled API fixtures to avoid sending unsolicited test invitations, while real account creation/role enforcement was already verified by the AWS suite. React reports reuse the predefined, bounded backend queries. No infrastructure shutdown was performed; the existing budget and keep-online rules continue to apply.

## Sign-in refinement and initial-account recovery — 15 October 2026

The user requested a simpler landing page and the frontend-design skill. The revised entry page provides one Sign in action and collapsed first-login/recovery help, with no promotional headline or motor illustration. The updated suite passed 23 browser scenarios, including entry-page desktop/mobile layout and axe checks.

Live account inspection found both original accounts still waiting for first password setup and lacking a verified email. With the deployed client's user-existence protection enabled, Cognito can show simulated reset-code delivery for such users. See [AWS password-reset error behavior](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pool-managing-errors.html#cognito-user-pool-managing-errors-password-reset). The current recovery page's masked address matched collegeproject@akshaykripalani.com. Previous human confirmation of SNS subscription and both received emails established ownership of that address. Its recovery email was marked verified, and AWS accepted a freshly generated invitation through AdminCreateUser RESEND. The NMIMS account was not changed. The user then reported that Cloudflare had forwarded the message but it was absent from the inbox. Read-only routing inspection confirmed the latest invitation was Forwarded with SPF/DKIM/DMARC passing. A subject search located its conversation in the destination Gmail Spam folder, and moving it to Inbox was verified in the visible Gmail state. The newest message is dated 15 October 2026 at 00:27 IST; the user must use that temporary password on the normal Sign in screen and choose their own permanent password. The message body was not opened and no credential was written into project files or the CLI log.

All operator AWS CLI commands, including failures, are appended to `AWS_COMMANDS.txt` with timestamps, purpose and exit status. Commands are executed through `scripts.aws_cli`; responses and sensitive authentication inputs are withheld. Source and evidence were committed in incremental milestones.

Cognito uses AWS’s default sender, `no-reply@verificationemail.com`, with the existing COGNITO_DEFAULT configuration; no external mail provider was introduced. See [AWS Cognito email settings](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-email.html).
