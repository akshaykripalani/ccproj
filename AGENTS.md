# AWS Project Notes

- Read `PRD.md` for the full project scope.
- Use the AWS CLI. Use Mumbai: `ap-south-1`.
- AWS account: `039379078306`. CLI user: `Akshay`. A teammate manages the account.
- The account uses the Free Plan. It had $100 in credits on 14 October 2026. The project budget is $50.
- Keep the project online until the user requests shutdown.
- Kinesis Data Streams, Firehose, and QuickSight are blocked. Do not use them.
- One EC2 instance simulates three motors. All motors start normally. Dashboard buttons cause faults.
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
