# Part 2. Design and implementation

## 2.1 Architecture and design decisions

The platform separates equipment simulation, ingestion, durable buffering, processing, live queries, historical analysis and browser delivery. This lets a processing interruption leave accepted telemetry queued while the dashboard and ingestion endpoint remain available. DynamoDB serves predictable current/recent access patterns; S3 and Athena serve historical aggregation without making every live refresh run SQL.

The implemented system has four Python Lambda entry points: Ingestion, Processor, ApiBackend and Notifier. Controls and report coordination are routes within ApiBackend, not separate deployed control/report functions. A scheduled Notifier publishes durable notification intents; Processor does not directly send email. These details refine the PRD's conceptual diagram and are shown in Figure 2.

| Decision | Rationale | Trade-off |
| --- | --- | --- |
| Single EC2 gateway, three simulated motors | Demonstrates compute, networking and shared remote controls without hardware | Gateway failure affects all motors; no EC2 fleet failover |
| API Gateway and SQS FIFO | IAM entry point, backpressure and ordered processing | One `factory` message group serializes this demonstration; not a high-throughput multi-factory design |
| DynamoDB plus S3 | Low-latency live reads plus inexpensive analytical archive | Cross-service writes need replay-safe design; no single global transaction |
| Threshold rules with consecutive counters | Repeatable fault demonstrations and understandable decisions | No learned anomaly model or predictive maintenance |
| Separate notification outbox | Alert recording does not depend on immediate SNS availability | Delivery is asynchronous and may duplicate across a publication/recording crash |
| Athena predefined queries | Demonstrates data engineering with bounded scan cost | Seven-date queries, 30-day horizon and application quota restrict exploration |
| Static React through CloudFront/private S3 | HTTPS, caching and independent UI releases | Browser rendering and polling; no SSR or push telemetry |
| Three CloudFormation stacks | Separate artifact bootstrap, application platform and simulator lifecycle | Deployment order and cross-stack outputs must be managed |

Figure 1 presents system context; Figure 2 shows AWS components; Figure 3 shows the simulator network boundary. Full-size diagrams and editable sources are in the diagram appendix.

## 2.2 Physical deployment and networking

The live application entry point is https://d1idggpc663p7f.cloudfront.net. Protected application requests go to https://9ojy2mmg65.execute-api.ap-southeast-2.amazonaws.com. The regional resources are in Sydney; CloudFront supplies edge delivery. Authentication redirects to the project's Cognito domain and returns to the exact configured `/callback` URL.

`ccproj-artifacts` owns the private versioned release bucket. `ccproj` owns the platform services, storage, identity, scheduling and monitoring. `ccproj-simulator` owns the gateway instance and VPC network resources. Resource identifiers and stack outputs are recorded in `docs/ccproj-deployment.json`; the report uses logical names where physical identifiers add no design information.

The simulator VPC uses `10.42.0.0/24`, with a public subnet `10.42.0.0/26` and an Internet Gateway/default route. The instance uses a public IPv4 address to reach AWS service endpoints. There is no NAT Gateway and no inbound security-group rule. Outbound HTTPS and DNS support API, DynamoDB, SSM, logs and software/release access. A public subnet does not imply that SSH or an application listener is exposed.

The instance is ARM `t4g.micro` with an encrypted 8 GiB gp3 root volume, standard CPU-credit mode and required IMDSv2. A systemd-supervised Python simulator starts at boot. SSM supplies management and release updates without opening SSH. Lambda uses Python 3.12 ARM64, 256 MiB memory and 30-second timeouts in the generated templates. Application Lambda functions are not deployed into this custom simulator VPC.

## 2.3 Telemetry lifecycle and failure semantics

1. The simulator generates a smooth synthetic reading for each reporting motor. The event ID remains stable if transmission must retry. A disconnected motor stops reporting while the other motors continue.
2. The instance role signs `POST /telemetry` with SigV4. API Gateway requires IAM authorization for this route. Human Cognito tokens do not substitute for that permission.
3. Ingestion parses and validates the full batch. It normalizes times, adds receipt time and computes a canonical SHA-256 batch identity. Only after SQS accepts the message does it return HTTP 202. This response means queued, not processed.
4. The FIFO queue uses the `factory` message group and explicit batch deduplication ID. Its retention is four days, visibility timeout 180 seconds, and redrive limit three receives. The matching FIFO DLQ retains messages for 14 days. Queue encryption uses SQS-managed encryption.
5. Processor validates the envelope relative to its original receipt time, allowing a legitimately accepted message to wait in a backlog. It checks event fingerprints before archival, then writes compressed date-partitioned history and processes each reading into DynamoDB.
6. S3 archive keys have the shape `telemetry/day=YYYY-MM-DD/{batchId}.json.gz`. Newline-delimited JSON includes receipt time. A cross-midnight batch is split by observed date. Deterministic gzip content and a conditional `IfNoneMatch` write prevent retries from creating unnecessary versions of the same batch object.
7. Each reading commits a DynamoDB transaction containing its deduplication marker, recent-reading item, revised device state and any alert transition/notification intent. Conditional revision checks retry up to five times when state changes concurrently. The marker stores a canonical fingerprint: reusing an ID with different measurements is an error.
8. Only a strictly newer observed timestamp replaces the current measurement or advances fault counters. Receipt time tracks liveness separately. An older event can be archived and stored as recent history without regressing the device state. A duplicate does not create another reading or episode.
9. Processor acknowledges a queue message after required archive and transactional operations complete. On the first failure in a FIFO batch, it returns that message and all subsequent unprocessed message IDs in `batchItemFailures`. Earlier committed work is safe to encounter again because event markers suppress recounting.

The event source mapping batch size is ten. A single batch can fail after an archive write or after some per-reading transactions have committed. Retries reconcile those partial outcomes; there is no atomic S3-plus-DynamoDB commit. SQS deduplication alone is insufficient because it has a bounded window; DynamoDB markers extend application-level retry handling to 31 days. The system does not claim exactly-once processing forever or permanent deduplication after markers expire.

## 2.4 Data model, indexes and retention

The on-demand Data table uses string `pk` and `sk` keys. Different item types support explicit query patterns without a relational join. Device metadata includes registered identity and configured thresholds in application configuration; latest state and rule counters are persisted. Controls use a separate on-demand table so requested scenarios are not mistaken for measured equipment conditions. Figure 5 maps the records and access patterns.

| Store/item | Key or layout | Principal contents and use | Retention |
| --- | --- | --- | --- |
| Data: device state | `pk=motor-01`, `sk=STATE` | Latest reading, lastSeen, revision, per-rule active/counter state | Current state; no expiring history window |
| Data: recent reading | `pk=deviceId`, `sk=READING#{observedAt}#{eventId}` | Measurement and receivedAt; time-range query and pagination | TTL at observed time +24 hours |
| Data: event marker | `pk=EVENT#{eventId}`, `sk=META` | Canonical fingerprint and archive key | TTL 31 days from processing |
| Data: alert episode | `pk=deviceId`, `sk=ALERT#{alertId}` | Rule, activation reading/time, active/resolved and resolution time | TTL 30 days |
| Data: notification intent | `pk=NOTIFY`, `sk=alertId` | Device/rule/reading, delivery state, SNS message ID | TTL 30 days |
| Data: report metadata | `pk=REPORT#{queryId}`, `sk=META` | Owner, validated parameters and query association | TTL seven days |
| Data: report quota | `pk=QUOTA#{UTC-date}`, `sk=REPORTS` | Atomic daily report-start counter | TTL two days |
| Controls: motor request | `pk=deviceId`, `sk=CONTROL` | Requested/applied modes, request/run IDs, acknowledgement timestamps | Current control record |
| Controls: gateway run | `pk=GATEWAY`, `sk=RUN` | Simulator run identity and start time | Current run record |
| S3 archive | Date partition / batch gzip object | Historical measurements including receipt time | Current and noncurrent versions bounded to 30 days |
| S3 report results | Private Athena output objects | Query result files and metadata | Seven-day lifecycle |

The sparse Data `Work` GSI partitions on `workStatus` and sorts on `workAt`. Only pending notification intents carry those attributes. After a successful publish is recorded, the attributes are removed, taking the item out of pending work queries. This avoids repeatedly scanning every device/history item.

DynamoDB TTL and S3 lifecycle expiration are asynchronous. API bounds enforce the recent window independently of physical removal. The release-artifact bucket has a 90-day lifecycle and frontend assets a 365-day lifecycle; these differ from telemetry retention. Stateful resources use retention policies to preserve established data across stack deletion/replacement. Operators must deliberately remove retained resources during a later authorized shutdown.

## 2.5 Fault detection, notification and motor control

Each device has independent temperature and vibration rule state. Temperature is breached only above 75 degrees Celsius; vibration only above 4.5 mm/s. Equality is healthy. A breached reading increments the above counter and resets the healthy counter. A healthy reading does the reverse. Counters saturate at three. The third consecutive breach activates an episode; the third consecutive healthy reading resolves it. An intervening opposite result resets the relevant sequence.

Activation writes an alert and notification intent in the same DynamoDB transaction as the triggering reading/state. Sustained breach does not create repeated activation intents. Resolution updates the existing alert instead of deleting it, and no recovery email is sent. Temperature and vibration may be tracked independently even though the operator selects one simulator mode at a time.

EventBridge Scheduler invokes Notifier once per minute. The worker reads up to 50 pending intents per invocation and checks confirmed SNS subscriptions. With none confirmed, it records `pending_confirmation` while retaining the work item. A successful SNS publish records `sns_accepted`, message ID and publication time, then removes the pending-index attributes. Failed attempts remain for a later run and raise an operational error. SNS uses a project KMS key for topic encryption.

`sns_accepted` describes provider acceptance, not inbox delivery. The actual demonstration has separate human confirmation that both fault emails arrived. A crash between SNS accepting a publication and DynamoDB recording success can cause another email on retry. Notification timing includes the scheduler delay and external email delivery, so it is not the same as telemetry processing latency.

Operator control routes write requests instead of directly changing device measurements. A request identifies the motor, requested mode, request ID and current gateway run. A separate simulator thread polls controls about every five seconds, applies a matching request and conditionally acknowledges it. The dashboard shows requested and applied states separately. A missing acknowledgement after 60 seconds displays a timeout; the request remains available for reconciliation.

Overheat and vibration modes gradually alter the generated measurements. Normal mode brings them toward baseline over about 30 seconds, after which the three healthy readings resolve an active rule. Disconnect suppresses only the selected motor's transmission. Reset-all issues three independent normal-mode requests and does not erase alert history. A stopped motor still reports with zero power and can be online; a disconnected motor eventually becomes offline. Figure 7 shows these state transitions.

## 2.6 Authentication, authorization and security

People and the gateway have separate trust paths. The gateway uses its EC2 IAM role and signed AWS requests. People sign in with the Cognito user pool. The browser is a public OAuth client without a secret and uses authorization code with PKCE S256, random state and exact registered redirect URLs. `openid email profile` scopes support sign-in and the configured protected routes. Figure 6 shows the interaction.

`oidc-client-ts` manages the browser exchange and session. Tokens live in per-tab session storage, not source/config files. Access and ID tokens last ten minutes; refresh tokens last one day. The API receives the access token, not the ID token. API Gateway validates the JWT issuer, audience/client and supported scope. ApiBackend enforces viewer/operator membership. Privileged operations additionally check current Cognito groups, preventing a still-valid older operator token from keeping removed privileges. Operators cannot remove their own operator role.

Read requests can renew authentication once after a 401. Mutations are not automatically replayed when their response is uncertain: retrying a control or invitation could repeat an action whose first outcome is unknown. Sign-out clears local state, revokes the refresh session where supported by the implemented flow, and visits hosted logout. Callback handling removes authorization-code parameters from the visible URL.

The API allows only predefined report identifiers and validated values. Each report metadata item records its requesting principal; another authenticated user cannot retrieve it merely by guessing its ID. Recent-history cursors are validated for the requested motor and key shape. Unknown device IDs and inappropriate roles are rejected server-side.

S3 buckets block public access and enforce secure transport. Frontend objects are read through CloudFront Origin Access Control; raw S3 origin access is denied. Historical and Athena-result buckets remain private. At-rest encryption covers S3, DynamoDB, EBS, queues and the SNS topic. IAM roles limit runtime service actions/resources; no access keys are embedded in the simulator or browser.

CloudFront sets CSP, HSTS, frame denial and content-type protection. The policy allows scripts and stylesheet elements from the same origin. Recharts requires inline style attributes for responsive charts, so `style-src-attr 'unsafe-inline'` is permitted specifically for that rendering need. This choice does not permit arbitrary inline scripts. Automated security/configuration checks are useful evidence, not a penetration-test certification.

The append-only CLI wrapper records timestamp, purpose, non-secret arguments and exit status, but not AWS responses. Sensitive inline inputs are rejected; protected temporary input files are used where necessary. Documentation and screenshots exclude passwords, tokens and mailbox messages.

## 2.7 Application API design

All human routes below require Cognito access tokens. Viewer or operator membership permits read/report access; controls and users require operator. Telemetry alone uses IAM. JSON responses set `Cache-Control: no-store`.

| Method and route | Request / result | Constraint |
| --- | --- | --- |
| `POST /telemetry` | `{readings:[...]}`; 202 accepted | IAM signed; validated 1-30 item batch |
| `GET /devices` | Three device views and server time | State, freshness, thresholds and requested/applied control |
| `GET /devices/{id}` | One device view | Registered ID only |
| `GET /devices/{id}/readings` | `from,to,limit,cursor`; readings and nextCursor | Last 24 hours; limit 1-1000 per page |
| `GET /alerts` | Optional device/time/state filters; alerts and subscription counts | Last 30 days; bounded history response |
| `POST /controls/{id}` | `{mode}`; 202 request record | normal/overheat/vibration/disconnect |
| `POST /controls/reset-all` | Per-device requests | Operator; acknowledgement remains asynchronous |
| `POST /reports` | `{report,start,end,deviceId?}`; report ID/status | Predefined type, validated dates and daily quota |
| `GET /reports/{id}` | Status, parameters, scanned bytes, result rows/error | Requesting owner only |
| `GET /users` | Cognito accounts and viewer/operator groups | Operator; current bounded list up to 100 users |
| `POST /users` | `{email,roles}`; Cognito invitation | Operator; generated temporary password sent by Cognito |
| `PUT /users` | `{email,roles}`; role assignment | Operator; cannot remove own operator access |

The API contract in `docs/API.md` is the integration reference. Validation, permission and query failures are shown explicitly by the UI; a successful request is not inferred from a button click or optimistic mode label.

## 2.8 Historical reporting and SQL

Glue defines the JSON archive schema with projected date partitions, avoiding a continuously running crawler. Athena scans the compressed history using a dedicated workgroup. The backend generates SQL from a fixed report map. Date and device parameters are validated before execution; the browser never supplies raw SQL.

| Report | Grouping | Calculated values |
| --- | --- | --- |
| Temperature | Motor and observed date | Average temperature, maximum temperature, reading count |
| Vibration | Motor and observed date | Count of readings above 4.5 mm/s |
| Power | Motor and observed date | Average power for running readings and count of running readings |

A common query stage deduplicates `eventId` with `row_number()` ordered by receipt time. This handles a resent measurement appearing in more than one archive envelope. Vibration counts breached readings, not the number of activated fault episodes. Stopped readings are excluded from the running-power average.

A report spans one to seven inclusive dates within the last 30 days. A 10 MiB workgroup scan cutoff bounds each query; an application-wide atomic quota allows 100 report starts per UTC day. These controls reduce exposure but do not form a complete monetary cap. Query state is asynchronous: React polls about every three seconds, then displays charts, tables and CSV when complete, or a clear failure/empty state. Report results are stored privately in S3 and exposed through the authorized backend. Figure 8 combines the reporting and recovery paths.

## 2.9 React implementation

`main.tsx` mounts the React application. `App.tsx` manages authentication, navigation and hash routes for overview, device detail, alerts, reports and users. `pages.tsx` provides the views; shared controls and chart/display elements live in `components.tsx`. `api.ts` centralizes protected requests, `auth.ts` handles OIDC, `hooks.ts` supplies polling/clock behavior, and typed contracts are in `types.ts`. CSS is separated into tokens, application styles and entry-page styles.

Overview shows motor counts, measurements with units, active faults and freshness. Device detail plots temperature, vibration and power through Recharts. Historical points are paginated in pages of up to 1000, then updated with a 30-second overlap and event-ID deduplication. Display history is bounded to 24 hours and 10000 points. Gaps longer than 25 seconds are represented as gaps rather than a falsely continuous line. Threshold references help interpret the temperature/vibration charts.

Live polling runs every ten seconds on relevant visible pages and pauses when the document is hidden. Requests are cancelled when their view/range becomes obsolete. A failed refresh preserves the last successful readings while showing an error/stale indication. A progressing browser clock uses server-time offset so an old response becomes visibly stale even when no new response arrives. Network requests have bounded timeouts.

Alerts support device, state and 1/7/30-day filters, retained resolution history and honest notification states. Reports validate the date window, show asynchronous progress and generate CSV downloads. Operators see fault/reset controls and user management; viewers do not. Backend enforcement remains decisive. Requested/applied controls and timeouts remain visible during remote operation.

The entry screen was revised to a concise sign-in card with collapsed initial-account help, following the user's preference against promotional copy. Responsive navigation supports mobile screens, controls have accessible names and landmarks, and reduced-motion preferences are handled. Automated axe checks cover tested entry, monitoring, reports, alerts and account views, but do not replace manual assistive-technology evaluation.

## 2.10 Deployment, releases and operational workflow

The generator produces three ordinary CloudFormation JSON templates. Resource metadata records purpose and constraints. Validation combines cfn-lint, CloudFormation Guard, code linting and tests. Deployment checks the AWS account and region rather than relying on an assumed default profile.

The workflow is: validate source/templates; package versioned backend and simulator releases; create/update artifact storage; deploy the platform with artifact keys; provision the simulator with platform outputs; seed the initial Cognito groups/accounts; generate public non-secret frontend configuration; build React; publish static assets; invalidate CloudFront and verify the served release. The EC2 updater waits for cloud-init before changing the running service, preventing a boot/update race.

Frontend publishing is separate from backend infrastructure deployment. Vite builds content-hashed bundles; `publish_frontend.py` uploads them and updates the entry point. Old hashed assets are preserved during a release so an existing page can finish loading its referenced files. `index.html` is not treated as an indefinitely cached immutable asset. `/config.json` supplies public endpoint, region and Cognito identifiers and contains no credentials. The recorded release was checked by fetching every served build asset and comparing SHA-256 hashes.

All operator AWS CLI commands pass through `scripts/aws_cli.py` and append to `AWS_COMMANDS.txt`, including unsuccessful operations. This is an execution audit, not a template of unexecuted commands. Runtime Lambda/EC2 SDK calls are not CLI commands and are not represented as individual entries in that file. Deployment and test scripts retain their own evidence outputs without writing secrets into the log.

CloudWatch captures seven-day Lambda/simulator logs and ten operational alarms for function/queue health. Equipment alarms are application rules; CloudWatch alarms monitor the platform. During failure demonstration, repeated poison-message processing errors were observed, the message entered the DLQ, its invalid envelope was inspected/corrected, and corrected work was redriven. Consumer interruption demonstrated continued queue acceptance and subsequent catch-up.

## 2.11 Recovery and later shutdown

Recovery is deliberately limited and independently verifiable. The object-version test overwrites/deletes a known test object and restores its prior version. `scripts/recovery.py` reads a bounded archive prefix, decompresses NDJSON, deduplicates event IDs and sorts by original observed time/event ID. It reconstructs state with original receipt/observation times in a separate disposable CloudFormation-managed DynamoDB table. It never writes the live state table and never calls SNS. Its archive listing is bounded to 10000 objects. This establishes a small reconstruction demonstration, not automated regional disaster recovery.

The recorded known three-device reconstruction and object restore took 70.641 seconds before verification/cleanup; the entire test took 137.105 seconds. Those timings depend on the small chosen fixture and AWS control-plane response and are not a promised recovery-time objective for 30 days of data.

No full live-stack teardown was run because the project must remain online. `docs/SHUTDOWN.md` specifies evidence export, ownership snapshots, simulator/platform/artifact stack deletion, and explicit handling of retained buckets, tables, user pool and KMS key. Versioned bucket cleanup must remove object versions and delete markers. KMS deletion has a required waiting period. Only project-owned resources may be removed, and billing must be rechecked after propagation delay.

## 2.12 Verification results and interpretation

| Verification layer | Recorded outcome | What it establishes |
| --- | --- | --- |
| Backend/infrastructure tests | 64 passed, plus Ruff, cfn-lint and Guard on all three templates | Domain, handler integration, controls, audit and infrastructure constraints in tested cases |
| Real AWS suite | 14 distinct latest-per-scenario passes across several runs | Actual services, queue buffering/DLQ, IAM/Cognito, reports, private hosting/cache and limited recovery |
| Controlled browser suite | 23 passed after entry-page refinement | Repeatable UI success/error/empty/auth/accessibility states using deterministic fixtures |
| Deployed browser full run | Four journeys passed; 275.73 seconds including setup/cleanup | Real hosted PKCE, monitoring/controls/recovery, reports/CSV, role persistence and logout |
| Final published smoke | Desktop/mobile hosted-login and live-chart smoke passed | Final entry-page release integration after the earlier full run |

The latest-per-scenario AWS summary is not a claim that all cases passed in one uninterrupted run. Original failed/interrupted runs remain in `docs/`. A browser selector initially chose a hidden Cognito form; it was corrected to use visible fields and the deployed journey rerun. Backend/deployment fixes included per-queue policies and waiting for cloud-init. The consolidated evidence preserves failures rather than silently discarding them.

The final AWS-stage snapshot recorded three healthy motors, enabled consumer, empty queue/DLQ counts, an online SSM-managed instance and ten OK alarms. This is a point-in-time snapshot. The demonstrated fault notifications have SNS message IDs plus the user's confirmation that both arrived. Automated tests cannot guarantee future AWS availability, external mailbox delivery, every concurrency pattern or every future dependency/policy change.

## 2.13 Cost model and course coverage

The captured 14 October 2026 Sydney model estimates USD 26.93 for 730 hours and USD 12.39 for 14 days, before credits/free allowances. It assumes three motors every ten seconds, 788400 monthly readings, bounded reports and a USD 5 allowance for variable services. The component model is in `evidence/budget-model.json`; pricing was queried through the logged AWS CLI during implementation.

| Monthly component | Estimated USD |
| --- | --- |
| EC2 t4g.micro | 7.7380 |
| One public IPv4 address | 3.6500 |
| 8 GiB gp3 volume | 0.7680 |
| One KMS key and ten standard alarms | 2.0000 |
| DynamoDB transactional writes | 3.3586 |
| DynamoDB reads and control polling | 0.5617 |
| S3 archive PUT operations | 1.4454 |
| FIFO SQS operations | 0.3942 |
| Lambda requests and duration allowance | 2.0119 |
| API/logs/storage/reports/frontend allowance | 5.0000 |
| Rounded model total | 26.93 |

These are historical planning estimates, not a newly queried price quote or final invoice. Actual usage must be measured. A recorded USD 0 budget reading was affected by billing delay and does not demonstrate zero cost. Budget thresholds are account-wide for the project period, so unrelated teammate spending may trigger them. Continued operation can exceed USD 50 over time; notification does not stop that automatically.

The implementation maps to the PRD's course outline through architecture, IAM, S3, EC2, DynamoDB, VPC, automation, CloudFront caching, SQS decoupling, Lambda/API serverless work, Glue/Athena data engineering and limited recovery. These are twelve direct practical areas out of seventeen, approximately 71%, plus partial security and monitoring/availability coverage. Orientation is supporting context; inter-network connectivity and certification preparation are not implemented features. This is a mapping to the supplied outline, not an independently verified college grading decision.

## 2.14 Known limitations and open acceptance items

The platform is an academic demonstration with a single simulated gateway. It has no hardware validation, safety certification, regional failover, full disaster-recovery automation, exactly-once email guarantee or unbounded historical analysis. DynamoDB TTL and S3 expiration are asynchronous. Single-group FIFO and small Lambda/instance settings suit the specified workload, not an established production capacity claim.

**Initial account sign-in remains unresolved.** The user's latest report was that a chosen password was rejected and reset mail did not arrive. The last read-only diagnostic still showed `collegeproject@akshaykripalani.com` enabled and `FORCE_CHANGE_PASSWORD`, with verified email and last modification at 15 October 2026, 00:27:37 IST. This suggests first-password completion has not been established for that account; the exact cause still requires diagnosis. Real automated hosted-login tests used disposable accounts and do not prove that this initial user's permanent password works.

Cognito's configured default email sender is `no-reply@verificationemail.com`. A fresh invitation had been accepted by AWS, forwarded by the mailbox routing service and found in destination Spam, then moved to Inbox. That delivery investigation does not prove later password-reset delivery or close the reported password problem. No password or reset code is included in submission evidence. The other initial account's first-access completion is also not claimed by this report.

Final actual-cost reconciliation, complete manual accessibility evaluation, production-scale capacity testing and a full user-authorized live teardown have not been performed. The report documents implemented behavior, bounded measured demonstrations and these remaining limitations separately.
