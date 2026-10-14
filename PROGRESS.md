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
- Current work: validate the migrated Sydney implementation, deploy, run live E2E/recovery exercises, and record actual resources/URLs/test results here. Commit milestones regularly.
