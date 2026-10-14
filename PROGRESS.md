# Implementation progress

Original goal: deploy the complete AWS portion of PRD.md, add extensive deployed end-to-end tests, log every AWS CLI command, and commit incremental milestones. React implementation remains the subsequent application stage; its hosting, Cognito, backend APIs, controls, and reporting infrastructure are in this AWS stage.

- All operator AWS commands must use scripts/aws_cli.py, which appends command arguments and exit status to AWS_COMMANDS.txt before/after invocation and withholds responses from the log.
- Active account must be 039379078306. User approved Sydney (`ap-southeast-2`) on 14 October 2026; it replaces Mumbai for deployment.
- Keep the Free Plan. No paid-plan upgrade or advanced-feature activation is authorized.
- $50 total service-usage ceiling before credit offsets. Notify at $20, $30, and $40; ask the user before stopping any resource for spending reasons. Keep online until user requests shutdown.
- SNS recipient: collegeproject@akshaykripalani.com. Confirmation/delivery must be recorded truthfully.
- Preserve three shared motors, initially healthy, fault controls and simulator acknowledgements, 24-hour recent readings, 30-day archive, three-reading activation/recovery, role enforcement, user management, and three bounded Athena reports.
- Code/templates are implemented. Before migration, 64 local tests, schema validation and CloudFormation Guard checks passed. Live tests have not run and were explicitly skipped while deployment was blocked.
- Sydney SQS creation succeeded in a temporary diagnostic; that queue was deleted. No project deployment existed when this goal resumed.
- All three stacks are deployed in Sydney: ccproj-artifacts, ccproj, ccproj-simulator. The initial shared-queue policy was fixed to separate per-queue policies; empty resources from the unsuccessful initial creation were checked empty and cleaned. RetainExceptOnCreate now prevents those empty first-create orphans while preserving established state.
- Platform API: https://9ojy2mmg65.execute-api.ap-southeast-2.amazonaws.com . Hosting: https://d1idggpc663p7f.cloudfront.net . Instance: i-098cf45e426dd3ab7. Full outputs are in docs/ccproj-deployment.json.
- Two live authentication tests passed, including actual hosted authorization-code/PKCE login. Live EC2 overheat/vibration activation/resolution, independent motor behavior, disconnection/reset, duplicate and older-event checks passed. The buffering test failed and is being investigated; the current live suite continues through DLQ/report/recovery exercises. Do not claim complete live acceptance yet.
- SNS subscription for collegeproject@akshaykripalani.com is PendingConfirmation. Fault notification intents correctly show pending_confirmation, not delivered. A user confirmation question is pending.
- Budget notifications at $20/$30/$40 were verified through AWS. Conservative 730-hour model is $26.93/month before credits/free allowances; see docs/budget-model.json. This is an estimate; actual usage still needs measuring.
- EC2 release updates now wait for cloud-init, fixing a first-start race. EC2 telemetry is running through the deployed signed pipeline.
- Current work: finish real E2E tests, repair failures, demonstrate reports/cache/recovery, measure results, write acceptance evidence, and leave the project online. React remains the later application stage as planned.
