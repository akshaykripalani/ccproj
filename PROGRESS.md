# Implementation progress

AWS implementation is underway. Scope: deploy the AWS infrastructure/backend and EC2 simulator; prepare frontend hosting and authentication configuration for the later React application.

- All operator AWS commands must use scripts/aws_cli.py, which appends command arguments and exit status to AWS_COMMANDS.txt before/after invocation and withholds responses from the log.
- Active account must be 039379078306; region ap-south-1.
- Budget-limit behavior and SNS recipients have been asked of the user and are pending. Continue independent implementation.
- No deployment yet. Never stop or tear down the project automatically without the agreed policy.
