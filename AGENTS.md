# AWS Project Notes

- Read `PRD.md` for the approved expansion. `PRD.old.md` records the completed original scope.
- Use the AWS CLI. Use Sydney: `ap-southeast-2` (user authorized the region change on 14 October 2026).
- AWS account: `039379078306`. CLI user: `Akshay`. A teammate manages the account.
- Never use the `provision` AWS profile/session or its resources; it belongs to the user's internship SSO sign-in. Verify the project account before accessing AWS resources.
- The account uses the Free Plan. It had $100 in credits on 14 October 2026. The project budget is $50.
- Keep the project online until the user requests shutdown.
- Kinesis Data Streams, Firehose, and QuickSight are blocked. Do not use them.
- One EC2 instance simulates three induction motors, a centrifugal pump, an air compressor, a cooling fan and a generator. Configurable deterioration profiles and manual controls demonstrate faults. Train locally and use a compact inference Lambda for five-minute predictive maintenance.
- Use simple Healthy/Warning/Fault labels. Transient overheating can cool/restart automatically; mechanical faults require manual repair. Preserve the dashboard design language.
- Do not set a shutdown date or scheduled teardown. Favor low-cost infrastructure.
- Send telemetry through API Gateway, Lambda, and SQS. Use Lambda to process it.
- Store current state and recent readings in DynamoDB. Store historical readings in S3.
- Use Athena to query S3 history. Use Glue Data Catalog for table definitions.
- Store the React build in S3. Use CloudFront to deliver it. Use Cognito for login.
- Use IAM roles for service access. Use CloudWatch for logs and alarms. Use CloudFormation for deployment.
- Never store access keys or secrets in project files or frontend code.

AWS CLI path on this computer:

```text
C:\Users\aksha\AppData\Local\Programs\Amazon\AWSCLIV2\aws.exe
```

Check the active identity with `aws sts get-caller-identity`.
