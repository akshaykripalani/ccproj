# Predictive Maintenance for Industrial Equipment

Status: completed and deployed, 27 October 2026. Verification is recorded in `docs/PREDICTIVE_ACCEPTANCE.md`. The completed original scope is archived in `PRD.old.md`.

## Product scope

Extend the deployed Sydney monitoring platform to seven simulated assets: three induction motors, a centrifugal pump, an air compressor, a cooling fan and a generator. Preserve the existing dashboard design, authentication, telemetry pipeline, alerts and historical reporting.

Each asset has configurable deterioration profiles, normally around 30 simulated minutes per failure episode. Include thermal and mechanical failure modes, varied load and noise, healthy operation, and accelerated demonstration speeds. Manual fault controls remain available. The simulator's hidden failure schedule is ground truth for supervised training only, never an inference feature.

Train a compact classifier locally to identify faults within the next five simulated minutes. Evaluate on independent simulation runs, compare against a simple trend baseline, measure precision/recall, false alarms and warning lead time, and disclose synthetic-data limitations. Deploy versioned model artifacts through a separate low-cost inference Lambda. Include reproducible training, evaluation gates, release selection and rollback.

Automatically stop, cool and restart recoverable transient overheating. Mechanical faults require an operator's explicit repair action. Persistent overheating escalates rather than repeatedly restarting. Keep the human workflow simple: Healthy, Warning, Fault, with short maintenance action text. Normal telemetry determines recovery without a separate operator verification workflow.

Expose predictions, equipment-specific measurements, profile controls and maintenance history in the existing React interface. Viewer/operator authorization applies to the new controls. Historical reports support all seven assets.

## Infrastructure and operation

Use account `039379078306`, explicit CLI profile `default`, and Sydney `ap-southeast-2`. Never use `provision` or its resources. Keep API Gateway, Lambda, SQS, DynamoDB, S3, Athena, Glue, CloudFront, Cognito, IAM and CloudWatch; CloudFormation owns infrastructure. Do not introduce Kinesis, Firehose, QuickSight, GPUs, managed always-on ML endpoints, NAT gateways or a second EC2 instance unless measurements justify a low-cost alternative. The $50 budget and $20/$30/$40 notifications continue. No shutdown date, scheduled teardown or automatic budget shutdown is authorized; remain online until requested.

## Deliverables and acceptance

1. Seven devices stream valid type-specific readings through the deployed pipeline.
2. Held-out evaluation and a live demonstration show predictions before threshold faults.
3. Overheating automatically cools/restarts; mechanical faults remain until explicit repair.
4. Profiles, accelerated timing, model version and maintenance history are usable in the dashboard.
5. Existing fault, report, authorization, ordering, deduplication and recovery behavior remains tested.
6. Deployment is reproducible and the previous model release can be restored.
7. Revise the supplied Springer LNCS DOCX into a concise report of the final system, with measured results and simple architecture/sequence diagrams. Preserve the source document and deliver visually checked DOCX/PDF outputs.
