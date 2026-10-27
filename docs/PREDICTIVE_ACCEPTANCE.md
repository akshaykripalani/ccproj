# Predictive maintenance acceptance — 27 October 2026

The approved expansion is deployed in account `039379078306`, Sydney, using only the explicitly selected `default` profile. The internship `provision` session and its resources were not used. The dashboard remains at https://d1idggpc663p7f.cloudfront.net. CloudFormation owns the update, including the separate inference Lambda, its scoped role/logs, a minute reconciliation schedule, asynchronous retry settings, three protected API routes and two additional alarms.

## Equipment and maintenance

One `t4g.micro` simulates three induction motors, a centrifugal pump, an air compressor, a cooling fan and a generator. Profiles configure enabled/disabled deterioration, 10–120 simulated-minute cycle lengths, thermal/mechanical/alternating/persistent thermal modes and 1×/5×/10× speeds. Defaults are enabled, 30 minutes, alternating mode, normal speed. A seeded timing factor varies cycles by about ten percent. Type-specific readings include motor speed/load, pump flow/pressure, compressor pressure, fan airflow and generator output/voltage/frequency.

Raw sensor windows, not the hidden schedule, drive learned predictions. Transient overheating stops/cools/restarts automatically. Mechanical faults latch a stop until explicit operator repair/reset. Persistent heat escalates once and remains stopped rather than looping through restarts. The interface preserves the Forge design with Healthy / Warning / Fault labels and short maintenance action text. Existing authentication, manual fault buttons, reports and alert history remain.

## Model evidence

The final selected model is `rf-b8af65a6f20e`, trained locally on CPU in a clean `.venv-ml` environment. `requirements-ml.lock.txt` pins dependencies. `models/README.md` gives the reproduction and release commands.

- 420 independent seeded episodes; 57,032 pre-fault windows.
- Entire episodes split into 273 training, 71 validation and 76 held-out test runs.
- 32 random-forest trees; depth ≤8; eight causal features over at most two simulated minutes.
- Five-minute warning horizon; validation-selected score threshold 0.80.
- Held-out precision **0.9027**, recall **0.9433**, F1 **0.9226**, healthy-window false-positive rate **0.0093**.
- Trend baseline precision **0.9812**, recall **0.8143**, F1 **0.8900**: the forest improves recall/F1 while producing more false positives.
- 51 failing test episodes detected; none missed at episode level. Median valid warning lead **5.0 simulated minutes**, minimum **1.67**. This does not mean every window warning was correct.
- Standard-library exported inference matched the training library on 500 held-out samples, including float32 input conversion.

The test set does not select hyperparameters or thresholds. Healthy episodes are included; post-fault readings are excluded from the warning evaluation. Synthetic runs share the simulator's assumptions, so these results do not establish real equipment accuracy. Scores are uncalibrated and must not be described as guaranteed failure probabilities.

Full evaluation: `models/rf-b8af65a6f20e/evaluation.json`. The 264 KB model JSON is loaded from private S3 and cached in the Lambda environment; inference needs no scientific Python packages, GPU or always-on ML host.

## Real AWS demonstrations

`predictive-live-tests.xml` passed in 402.17 seconds, including setup/cleanup of disposable Cognito accounts. `predictive-live-evidence.json` records the model version and stored observations:

| Scenario | Stored warning observation (UTC) | Active-fault observation (UTC) | Outcome |
| --- | --- | --- | --- |
| Pump overheating | 26 Oct 21:44:18.450 | 26 Oct 21:44:48.577 | Automatic cooldown/restart |
| Compressor mechanical fault | 26 Oct 21:46:29.101 | 26 Oct 21:46:59.228 | Remained stopped until operator repair |

Both profiles ran at 10×, so thirty wall-clock seconds equal five simulated minutes. These observations compare a stored prediction with the later three-reading active-fault state, not necessarily the first raw threshold crossing. Viewer profile writes were rejected, all seven assets reported online, generator metrics were present and all maintenance event categories were recorded. The test restored enabled, normal-speed 30-minute profiles.

`predictive-persistent-live-tests.xml` passed in 298.33 seconds. A persistent thermal fault stayed stopped, escalated to Repair needed, retained the same cooldown request identity rather than retrying, and recovered after manual repair. `predictive-persistent-evidence.json` records the episode and escalation. Its profile was restored afterward.

## Model promotion and rollback

A second independently evaluated candidate, `rf-2f7930ddaf26`, was published and selected through CloudFormation. Its version appeared in a live DynamoDB prediction. The selected original model was then restored through the same deployment path and also verified on a new prediction. `model-promotion-rollback.json` records both observations. The simulator instance was unchanged by those model/backend updates.

`scripts.promote_model` supports an evaluated version argument. `scripts.release_backend` updates Lambda code/model selection without restarting or reprovisioning the simulator. Failed evaluation gates do not replace the selected local release. The candidate's test results are recorded separately and are not substituted into the reported final-model results.

## Local checks and deployment

82 local backend/infrastructure tests passed, including validation of new equipment telemetry, model warnings on unseen episodes, mechanical latching, thermal cooldown, profile permissions, stale commands and prediction ordering. Existing pipeline tests continue to cover deduplication, older messages, storage retries, alerts and reports. CloudFormation schema validation, CloudFormation Guard and Ruff passed. The React production build and 38 controlled browser scenarios passed, including new seven-asset/profile/repair/mobile checks and accessibility checks.

The simulator stack resolved a newer Amazon Linux image and replaced its EC2 instance. Its startup took longer than the CLI waiter's default bound; the already-running SSM update subsequently completed successfully. The update helper now polls for up to ten minutes without resending the command. The current instance is recorded in `ccproj-deployment.json`; the original instance belongs to the historical October 14 evidence. The account/region/resource constraints and existing retention policies were preserved.

## Cost and operating policy

`predictive-pricing.json` captures current Sydney ARM compute and DynamoDB rates through the logged AWS Price List API. The global pricing endpoint is in us-east-1; project resources remain in Sydney. Initial CloudWatch observations recorded 84 inference calls averaging **699.52 ms**, maximum **2586.45 ms**, including cold/release transitions. These are operational samples, not a steady-state benchmark.

`predictive-budget-model.json` conservatively estimates **$45.47 per 730-hour month** for the expanded system, or **$10.46 for an illustrative seven days**, before credits/free allowances. Inference Lambda itself is approximately **$1.08/month**, including requests and a one-second/256 MiB allowance. Database activity, not model compute, is the larger variable component. Baseline non-ML infrastructure rates retain the October 14 snapshot; this is a planning model, not an actual bill or hard cap.

No second EC2, GPU, managed ML endpoint, NAT gateway, provisioned Lambda concurrency or paid-plan upgrade was added. The $50 budget and $20/$30/$40 notifications remain. **There is no shutdown date or scheduled teardown.** The deployment stays online until the user requests shutdown.

## Updated report

`assignment_docs/updated/Cloud_Equipment_Monitoring_LNCS.docx` and its matching PDF describe the final system in approximately 2,350 words and eight pages, with three simple diagrams and six real references. Layout follows the supplied Springer LNCS template and official author guidance. Every page is rendered and reviewed using a dedicated hidden Word instance and Poppler because LibreOffice is unavailable. The source Downloads document is untouched.

The manuscript includes the five student authors in alphabetical first-name order, followed by Rama Varshney, Assistant Professor, and all six confirmed emails. They share the Computer Engineering affiliation at Mukesh Patel School of Technology Management and Engineering, NMIMS, Mumbai. Author order does not indicate contribution. `assignment_docs/updated/authors.json` makes the author block reproducible. Artifact hashes and visual checks are in `report-review.json`.

## Final verification and handoff

Five distinct deployed browser journeys have passing latest results in `predictive-browser-acceptance.json`: real hosted login/live charts/mobile viewer; cooldown and mechanical repair; all three Athena reports/CSV; persistent team-role changes; and generator/model detail. Initial failed runs are retained. The first failures were selectors that did not account for the Alerts badge and hidden model-detail text; the remaining report retry concerned a Windows lock on an existing screenshot file. The report scenario passed after moving screenshots into `predictive-ui/`. The launcher now restores shared equipment through the authenticated API even if the browser fails. Successful current screenshots are in that folder.

Final review also covered a new thermal episode following manual repair. The controller now accepts the applied repair command as a running state for a later automatic thermal response; a healthy repaired row no longer offers an unnecessary reset action. The regression passed locally and on AWS (`predictive-after-repair-live-tests.xml`, 171.89 seconds; `predictive-after-repair-evidence.json`).

`predictive-deployed-evidence.json` records the final read-only snapshot: all seven assets running with no active rules or prediction warnings, enabled 30-minute/1× profiles, selected model rf-b8af65a6f20e, one running project EC2, enabled processing, no dead-letter backlog and twelve OK alarms. All eleven published build files matched the local SHA-256 hashes. Existing SNS and budget policies remain in place. No test account, temporary recovery infrastructure or shutdown schedule was left by this work.
