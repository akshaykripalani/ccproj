# End-to-end implementation plan

This historical plan groups the completed original scope in PRD.old.md into three implementation chats. The original PRD was archived on 27 October 2026; this plan does not define the upcoming expansion. Follow AGENTS.md and the user's current requirements. Each part was intended to leave working code, validation results, and a written handoff for the next chat.

Implementation update, 14 October 2026: the user subsequently requested the **entire AWS portion** together, followed by the UI. Both are now implemented and deployed, including EC2 operation, Cognito, protected control/user-management/report APIs, the React dashboard, SNS delivery and recovery demonstrations. Browser acceptance covers hosted login, real chart data, controls/faults/recovery, reports and role management. Do not restart the infrastructure or replace the live EC2 simulator with a local process. Use PROGRESS.md, docs/AWS_ACCEPTANCE.md and docs/API.md as the current handoff; the part boundaries below preserve the original planning context.

## Part 1: Infrastructure and telemetry core

- Establish append-only AWS command logging before the first AWS CLI invocation. Check the active account is 039379078306 and use ap-southeast-2.
- Validate service access, relevant quotas, deployment permissions, and current Sydney costs. Choose resource sizes, set cost controls, and resolve the budget-limit rule before unattended operation. The $50 ceiling applies before credit offsets; keep the project online until shutdown is requested.
- Define telemetry schemas, DynamoDB access patterns, thresholds, archive layout, retention, API contracts, and simulator control/acknowledgement contracts.
- Implement CloudFormation infrastructure, scoped IAM roles, API Gateway, ingestion Lambda, SQS/DLQ, processing Lambda, DynamoDB, private versioned S3 archive, SNS, and bounded CloudWatch logging/alarms. Protect each deployed route appropriately from the outset; Cognito infrastructure can be established here for later dashboard routes.
- Build the local Python simulator with three initially healthy motors, stable retry identities, plausible measurements, and fault/test modes.
- Implement retry-safe processing, duplicate handling, ordering protection, three-reading fault activation/recovery, alert history, and notification state. Explicitly account for partial storage/notification failures.
- Verify real AWS ingestion, processing, current/recent state, archival, fault rules, rejected input, and duplicate/older events. Email confirmation may remain recorded as pending.

Completion gate: a local simulator sends signed telemetry through the deployed pipeline; storage and fault processing work and have meaningful tests. Record resource identifiers and validated API contracts for Part 2.

## Part 2: Dashboard, authentication, controls, and reports

- Build the React overview, device charts, active/historical alerts, report views, operator demo controls, and user-management page, including loading/error/expired-session/stale-data states.
- Complete Cognito hosted login with authorization-code/PKCE, access-token API authorization, viewer/operator roles, sign-out, and the two initial accounts required by the PRD.
- Implement protected read APIs, operator control APIs, and user management. Verify permissions directly against the APIs, including viewer-only and unauthenticated callers.
- Complete dedicated requested/applied control records, simulator polling and acknowledgements, stale-request protection, reset-all, gradual recovery, and fresh-run initialization. Verify control polling continues when an individual motor disconnects.
- Implement Glue table definitions, a bounded Athena workgroup, three predefined historical reports, asynchronous report status/results, and frontend charts/tables.
- Deploy the React build to its private S3 bucket and deliver it through CloudFront. Wire the actual deployed HTTPS callback URL into Cognito.
- Demonstrate the complete browser journey against AWS using the local simulator: login, live monitoring, motor faults, outage/reset, retained alert history, user roles, and reports.

Completion gate: the hosted dashboard supports all required user journeys against real AWS services. Part 3 replaces the local simulator with EC2 and completes operational demonstrations.

## Part 3: EC2 operation, acceptance evidence, and handover

- Deploy one small EC2 simulator through CloudFormation with the required VPC/subnet/routing/security group, instance role, supervised process, and repeatable updates. Include EBS and public IPv4 costs; avoid a NAT gateway.
- Verify all three motors start normally and the simulator keeps running independently of the developer computer. Verify faults, disconnection, control acknowledgements, and gradual reset through the hosted dashboard.
- Run and document every acceptance scenario in PRD.old.md section 12, including buffering during processing interruption, DLQ isolation/redrive, bounded load tests, authorization, and CloudFront cache updates.
- Restore a versioned test archive object and rebuild a separate test state table from history while preserving event times and suppressing replay notifications. Measure recovery and its limits.
- Verify 24-hour recent-reading retention, 30-day archive/version retention, bounded query scans, logs/alarms, and actual observed latency/usage/costs.
- Complete architecture/course mapping, screenshots or recordings, query/recovery evidence, deployment instructions, operations guidance, and later user-requested teardown instructions. Reproducibility checks must use an isolated test environment and stay within the budget.
- Leave the project online. Do not schedule teardown. Record external acceptance dependencies such as SNS subscription confirmation accurately.

Completion gate: the project operates end to end from EC2 to the hosted dashboard; all acceptance results are recorded as passed, failed, or pending with evidence and reasons.

## AWS command record

Use AWS_COMMANDS.txt as an append-only text record throughout all three parts. Before executing any AWS CLI command, append the timestamp, purpose, region/profile where applicable, and the command; append its outcome/exit code afterward. Include read-only commands, validation, deployment, retries, uploads, and failure/recovery commands. Never overwrite or truncate earlier entries.

Never record access keys, passwords, authorization headers, tokens, or secret values. Pass sensitive input through appropriate secure mechanisms and record a redacted command with a clear note when necessary. Do not copy sensitive CLI output into the record. Commands remain useful for review, but entries involving temporary files or redacted input need explanatory context to be reproducible.

## Handoff between chats

At the end of each part, create or update PROGRESS.md with completed work, deployed resource identifiers/URLs, commands to build/test/run, actual verification results, cost observations, known issues, pending external actions, and the precise next tasks. Do not place credentials or tokens in it.

Start the next chat with: "Read AGENTS.md, PRD.old.md, IMPLEMENTATION_PLAN.md, and PROGRESS.md. Continue Part N from the recorded state, inspect existing AWS resources before changing them, and append every AWS command to AWS_COMMANDS.txt."

If only two chats are desired, combine Parts 2 and 3. Three parts provide a clearer boundary between application implementation and full deployment/acceptance work.
