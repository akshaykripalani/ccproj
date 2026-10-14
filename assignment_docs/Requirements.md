# Part 1. Requirements specification

## 1.1 Project identification and problem

**Project:** Cloud-Based Industrial Equipment Monitoring and Fault Detection. **Context:** an academic Cloud Computing project using AWS. **Deployment:** Asia Pacific (Sydney), `ap-southeast-2`. **Report date:** 15 October 2026.

Equipment monitoring needs a reliable way to collect measurements, identify sustained problems, present current conditions and inspect earlier operation. A direct connection from a device to a dashboard does not provide durable buffering, historical analysis or a clear recovery path. This project implements those responsibilities as separate cloud components and demonstrates them using three simulated motors.

One EC2 instance represents a factory gateway. It emits temperature, vibration, power and operating state for `motor-01`, `motor-02` and `motor-03`. The measurements are synthetic; no physical sensors or factory integration are claimed. All motors begin healthy. An operator deliberately introduces faults through the dashboard, observes the resulting readings and alerts, and then restores normal operation.

## 1.2 Objectives and boundaries

The system must demonstrate authenticated telemetry ingestion, queued processing, current and historical storage, deterministic fault detection, email notifications, a protected interactive dashboard and bounded historical SQL reports. Infrastructure must be reproducible through CloudFormation and the AWS CLI. Failure demonstrations must cover duplicate events, processing interruption, invalid messages and limited recovery.

The project uses the existing AWS Free Plan and a USD 50 service-usage ceiling before credits. The account initially had USD 100 credits recorded on 14 October 2026. Credits offset billing; they do not increase the agreed project ceiling. Notify at USD 20, 30 and 40, and obtain the user's agreement before stopping resources for spending reasons. Keep the deployment online until shutdown is requested. Budget alerts are notifications, not a hard spending cap.

Sydney replaces the original Mumbai deployment choice with the user's approval after managed-account restrictions prevented the required Mumbai resource creation. Kinesis Data Streams, Data Firehose and QuickSight are excluded. SQS provides buffering, S3 stores history, Athena queries it, and the React dashboard supplies visualization.

Outside scope: physical hardware, IoT Core/MQTT, machine learning, WebSockets, public self-registration, social federation, arbitrary SQL, editable fault thresholds, container orchestration, relational databases, multi-region failover, production industrial safety decisions and a general infrastructure administration UI.

## 1.3 Actors and user journeys

| Actor | Required journey | Access boundary |
| --- | --- | --- |
| Viewer | Sign in, inspect all motors and recent charts, filter alerts, request historical reports and download report CSV | Authenticated read/report routes; report results belong to the requesting principal |
| Operator | Perform viewer journeys, request individual faults/reset-all, invite users and change viewer/operator roles | Server-side operator enforcement; current group membership checked for privileged requests |
| Simulator gateway | Publish batches and poll/acknowledge requested motor modes | IAM instance role and signed ingestion requests; no human password |
| Infrastructure maintainer | Deploy/update, inspect logs and queues, demonstrate failures/recovery, export evidence and later perform authorized cleanup | Authorized AWS CLI identity; all operator AWS commands appended to the command file |

The two initial team/evaluator accounts were provisioned with both viewer and operator roles. Creating a login account does not subscribe it to equipment email. SNS email subscriptions require their own confirmation. The confirmed project notification mailbox is `collegeproject@akshaykripalani.com`.

## 1.4 Functional requirements and implementation traceability

| ID | Required behavior | Implementation and evidence |
| --- | --- | --- |
| FR-01 | Three initially healthy motors; readings every 10 seconds; gradual synthetic values; independent normal, overheat, vibration and disconnect modes | `simulator/main.py`; actual EC2 fault/recovery and bounded burst/stopped-motor tests |
| FR-02 | Authenticate simulator with IAM; validate complete schema and registered IDs; return accepted only after queuing | `backend/ingestion.py`, `backend/domain.py`; signed malformed-input rejection and live pipeline tests |
| FR-03 | Batch queued processing, retry safety, duplicates, older events, partial failures and DLQ isolation | `backend/processor.py`; transaction tests, duplicate/order live test, real poison-message retry/redrive |
| FR-04 | Latest state and freshness, stopped versus offline, 24-hour recent history, 30-day archive and bounded object versions | Data table, API time filters and S3 lifecycle; stopped/offline, archive and retention-configuration evidence |
| FR-05 | Activate after three consecutive threshold breaches; resolve after three healthy readings; one notification intent per episode; retain alert history | `backend/domain.py`, processor and notifier; actual fault activation/resolution, confirmed SNS acceptance and human inbox receipt |
| FR-06 | React overview, device charts, alerts, reports, controls, users; loading, errors, empty results and stale data; 10-second refresh | `frontend/src/`; 23 controlled browser scenarios, four deployed journeys and final hosted-login/chart smoke |
| FR-07 | Cognito code/PKCE login, access-token API protection, sign-out/expiry, viewer/operator backend enforcement | `frontend/src/auth.ts`, JWT authorizer and backend role checks; hosted PKCE, direct API rejection and role-revocation tests; initial-account recovery remains open |
| FR-08 | Three predefined date/device reports over S3 using Glue/Athena; bounded inputs, scan limits, asynchronous status/results | `backend/domain.py:report_sql`, `backend/api.py`; known-data cross-checks for all three reports and real UI charts/CSV |
| FR-09 | Useful bounded logs, Lambda and queue alarms, operational notification and deliberate failure evidence | CloudWatch log groups, ten alarms, SNS; recorded health snapshot and intentional processing-failure logs |
| FR-10 | CloudFormation/CLI deployment, private frontend hosting, restricted EC2 networking, version restore and separate-table reconstruction | `infra/`, deployment/recovery scripts; template validation, cache/private-hosting tests and measured limited recovery |
| FR-11 | Shared independent motor controls with request/run matching, requested versus applied modes, reset behavior and timeout visibility | Controls table, API, independent simulator polling and dashboard; actual acknowledgements, reset, disconnect and unaffected-motor checks |

The table maps feature implementation to evidence. A passing test verifies its defined scenario, not every possible future fault. Initial-account access is an explicit acceptance exception rather than an omitted requirement.

## 1.5 Telemetry contract

| Field | Meaning and validation |
| --- | --- |
| `schemaVersion` | Integer 1; no implicit alternative schemas |
| `eventId` | Stable across retries; 1-160 characters from the permitted identifier alphabet; run/device/sample identity |
| `deviceId` | One of the three registered motor IDs |
| `observedAt` | UTC ISO-8601 event time, normalized to milliseconds; accepted within last 24 hours with up to 60 seconds future skew |
| `temperatureC` | Finite number from -40 to 200 degrees Celsius |
| `vibrationMmS` | Finite number from 0 to 100 millimetres/second |
| `powerWatts` | Finite number from 0 to 100000 watts |
| `operatingState` | `running` or `stopped` |

The request body contains only `readings`, an array of 1-30 readings. Each reading contains exactly the documented fields. Booleans are rejected as numeric values, as are NaN/infinity, duplicate IDs within a batch and unknown devices. Receipt time is added by ingestion; an anomaly label is not accepted as a measurement field. API request bodies are bounded to 65536 bytes.

## 1.6 Non-functional requirements

| Area | Target or constraint | Implemented measure / qualification |
| --- | --- | --- |
| Latency | Normal-load ingestion-to-current-state target under 30 seconds | Recorded sample 5.063 seconds including polling; not a percentile SLA |
| Freshness | Poll relevant views every 10 seconds; offline after 60 seconds without a valid processed receipt | Server timestamps, browser clock progression, observed/last-seen distinction and stale warning |
| Integrity | Retries must not recount events, regress latest state or repeatedly activate the same episode | Stable IDs, canonical fingerprints, conditional archive writes and DynamoDB transactions |
| Security | Authenticated ingestion and human APIs, private history/assets at origin, role-based mutations, encryption and no stored credentials | IAM/SigV4, Cognito/JWT, CloudFront OAC, HTTPS, scoped roles and command-log filtering |
| Cost | Small bounded demonstration within agreed service-usage budget | Small ARM instance, no NAT, on-demand data services, retention, query limits and budget emails; no automatic spending stop |
| Operability | Reproducible infrastructure, bounded logs, failure isolation, command audit and future cleanup procedure | Three CloudFormation stacks, seven-day logs, DLQ, logged CLI wrapper and shutdown runbook |
| Usability | Desktop/mobile, clear states, accessible controls and minimal entry copy | Responsive layout, keyboard/reduced-motion support and automated axe checks; full manual accessibility audit not claimed |
| Recovery | Demonstrate object-version restoration and reconstruction without disturbing live state | Disposable recovery table, original times, deduplication and no notification publication; no regional DR guarantee |

## 1.7 Acceptance and submission completion

Acceptance uses normal operation, individual faults, reset/disconnect, stale versus stopped readings, role checks, chart pagination, historical report accuracy, buffering, DLQ recovery, private hosting/cache updates and limited reconstruction. The original PRD acceptance scenarios remain authoritative. Recorded evidence is indexed in Part 4 rather than replaced by this document.

Implementation acceptance is supported by 64 backend/infrastructure tests, 14 distinct live AWS scenarios consolidated across runs, 23 controlled browser scenarios, four deployed browser journeys and a later desktop/mobile smoke. These counts overlap in feature coverage and must not be added into a single number of independent end-to-end tests.

Before a fully unqualified final demonstration, resolve the initial account's password setup/recovery problem and verify that person's sign-in. Before reporting a final actual project cost, reconcile the delayed AWS billing data with the project period and shared-account activity. Full production teardown is deliberately deferred until the user requests shutdown.
