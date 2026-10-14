# AWS application integration contract

Read public `/config.json` from the CloudFront URL for `apiUrl`, `clientId`, `userPoolId`, `loginDomain`, callback/logout URLs, and Sydney region. These values contain no credentials. The deployed URL and resource IDs are recorded in `docs/ccproj-deployment.json` after deployment.

## Authentication

Browser login uses Cognito's hosted `/oauth2/authorize` endpoint, `response_type=code`, scopes `openid email profile`, a fresh random `state`, and PKCE S256. Redirect to the exact configured `/callback`; exchange the code at `/oauth2/token` with the verifier. The client has no secret. Keep credentials/tokens out of source and logs. Send the access token (not ID token) as `Authorization: Bearer ...`. Access/ID tokens last ten minutes; refresh tokens last one day. Sign out through hosted logout and clear the application session. The initial accounts receive Cognito invitations; operators can invite further users.

API Gateway validates JWT issuer, client audience, expiry and a supported access-token scope. The backend requires viewer/operator groups and verifies the current operator group before privileged actions. The IAM-protected administrative password flow exists for CLI end-to-end test authentication, not the browser login flow.

## Routes

| Method/path | Role | Behavior |
| --- | --- | --- |
| `POST /telemetry` | IAM-signed simulator | Body `{readings:[...]}`. 1–30 readings; 202 means queued. Invalid reading batches return 400. |
| `GET /devices` | Viewer/operator | Three device views, latest readings/rules, freshness, metadata and requested/applied controls. |
| `GET /devices/{deviceId}` | Viewer/operator | One device view. |
| `GET /devices/{deviceId}/readings` | Viewer/operator | `from`, `to`, `limit` (1–1000), optional `cursor`. Bounds: last 24 hours. Returns readings and `nextCursor`. |
| `GET /alerts` | Viewer/operator | Optional `deviceId`, `from`, `to`, `state=active|resolved`. History remains after reset; includes honest email status and subscription counts. |
| `POST /controls/{deviceId}` | Operator | Body `{mode:normal|overheat|vibration|disconnect}`. Returns 202 pending request. |
| `POST /controls/reset-all` | Operator | Requests normal mode separately for all three motors. |
| `POST /reports` | Viewer/operator | Body `{report:temperature|vibration|power,start:YYYY-MM-DD,end:YYYY-MM-DD,deviceId?:motor-01}`. 1–7 dates within last 30 days; returns report ID/status. |
| `GET /reports/{reportId}` | Owning user | Query status; successful rows and bytes scanned. Cross-user access denied. |
| `GET /users` | Operator | Invited accounts and viewer/operator roles. |
| `POST /users` | Operator | Body `{email,roles:[viewer,operator]}`; Cognito invitation. |
| `PUT /users` | Operator | Assign roles to an existing account; operators cannot remove their own operator role. |

Device IDs are `motor-01`, `motor-02`, `motor-03`. Telemetry fields and units follow PRD.md. All timestamps are UTC ISO-8601, normalized to milliseconds.

## Monitoring behavior

Poll relevant live views every ten seconds. After a control request, refresh current state immediately and poll it every second while any control is pending, returning to ten seconds once controls are acknowledged or their sixty-second acknowledgement window expires. Use server timestamps and elapsed client time to bound fast polling even when subsequent requests fail. Hidden pages pause requests. Offline means no valid processed receipt within sixty seconds; display last-seen/observed times so a processing backlog is distinguishable from fresh telemetry. A stopped motor still reports and can remain online. Controls report pending until the simulator acknowledges the matching request and run. A request unacknowledged for sixty seconds displays failed/timed out; it remains available for reconciliation. Overheat/vibration changes the actual generated measurements; alerts activate after three breached readings and resolve after three healthy readings. Normal recovery approaches baseline within about thirty seconds.

Temperature threshold: above 75 C. Vibration threshold: above 4.5 mm/s. Thresholds are project configuration in `backend/domain.py`; no dashboard threshold editor is required.

Email states include `pending`, `pending_confirmation`, and `sns_accepted`. SNS acceptance is not proof of inbox delivery. A scheduled durable outbox retries failures. Exactly-once email delivery is not promised: a crash after SNS acceptance but before recording the message ID can duplicate a notification.

## Historical reports and limits

Temperature report returns average, maximum and reading count per motor/date. Vibration returns breached-reading count (not alert episodes). Power returns average while running and running-reading count. SQL is predefined, event IDs are deduplicated, dates/devices validated, and results stored privately. A workgroup enforces a 10 MiB scan ceiling per query; the application limits the project to 100 report starts per UTC day. Live pages use DynamoDB, not Athena.

Recent-reading TTL is 24 hours and archive current/noncurrent object retention is bounded to 30 days. DynamoDB TTL and S3 lifecycle deletion are asynchronous; API date filters enforce the live-history window independently of physical deletion.
