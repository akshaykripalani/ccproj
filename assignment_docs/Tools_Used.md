# Part 3. Tools and technologies used

## 3.1 AWS service inventory

| Service/tool | Use in this implementation | Why it is needed |
| --- | --- | --- |
| Amazon EC2 and EBS | One ARM gateway with an encrypted gp3 boot disk | Runs the persistent motor simulator and supervised process |
| Amazon VPC, subnet, route table, Internet Gateway and security group | Restricted public-subnet egress, no inbound rules | Network boundary and connectivity without NAT Gateway cost |
| AWS Systems Manager | Managed-node health and remote release commands | Operates the gateway without SSH ingress |
| Amazon API Gateway HTTP API | IAM telemetry entry and JWT-protected human routes | Separates device and browser authentication at the API boundary |
| AWS Lambda | Ingestion, Processor, ApiBackend and Notifier | Event-driven backend compute without continuously running application servers |
| Amazon SQS FIFO and FIFO DLQ | Ordered queue, retry/partial failure and failure isolation | Decouples producers from storage/processing and supports recovery demonstrations |
| Amazon DynamoDB | Data/Controls tables, transactions, TTL and sparse Work index | Current state, recent history, controls, deduplication, report ownership and notification intent |
| Amazon S3 | Release artifacts, private frontend, compressed history and private query outputs | Different policies/lifecycles for application assets, historical records and results |
| Amazon Athena | Three bounded on-demand SQL reports | Historical aggregation without a continuously running database engine |
| AWS Glue Data Catalog | Archive table/schema and date projection | Makes S3 JSON history queryable by Athena without a persistent crawler |
| Amazon SNS | Confirmed equipment and operational email subscription | Publishes asynchronous fault and platform notifications |
| Amazon EventBridge Scheduler | One-minute notification worker invocation | Retries durable pending notification work independently of ingestion |
| Amazon Cognito | Hosted login, user pool, public PKCE client, viewer/operator groups and invitations | Human account and session management |
| Amazon CloudFront and Origin Access Control | HTTPS static delivery, caching, origin restriction and headers | Distributes React while keeping S3 origin private |
| AWS IAM and STS | Service/instance roles, authorization and active account identity check | Grants runtime access without embedded access keys |
| AWS KMS | SNS topic encryption key | Protects stored notification messages using managed key access |
| Amazon CloudWatch | Bounded logs, metrics and ten operational alarms | Failure diagnosis and platform health evidence |
| AWS Budgets and Pricing API | Threshold notifications and captured price inputs | Tracks the agreed service-usage budget and supports the documented estimate |
| AWS CloudFormation | Bootstrap/platform/simulator templates and stack lifecycle | Reproducible, reviewable infrastructure deployment |
| AWS CLI v2 | All operator AWS operations through a logging wrapper | Executes deployment, verification and recovery while retaining an append-only command audit |

No Kinesis, Firehose, QuickSight, IoT Core, external email delivery provider, container runtime or relational database is required. Cognito uses its default AWS email sender. SNS mail and Cognito account mail have separate purposes and confirmation/recovery behavior.

## 3.2 Application languages and libraries

Version values below come from the committed manifests/lockfile, not a claim about the newest available versions. Frontend values are declared package ranges; the package-lock file records exact resolutions. Python deployed SDK and development lock versions are explicitly pinned.

| Technology | Recorded version/constraint | Actual use |
| --- | --- | --- |
| Python | Lambda runtime 3.12; local project environment 3.11.8 | Backend, simulator, infrastructure generator, deployment and test tooling |
| boto3 / botocore | Runtime boto3 1.43.113; development lock boto3/botocore 1.43.113 | AWS SDK clients, role-based calls, signing and DynamoDB transaction serialization |
| React / React DOM | `^19.3.1` | Browser component rendering and state |
| TypeScript | `^7.0.2` | Typed API contracts, component props and build-time checking |
| Vite / React plugin | `^8.3.4` / `^6.1.2` | Development tooling and production asset bundling |
| Recharts | `^3.10.1` | Recent telemetry and historical report charts |
| oidc-client-ts | `^3.5.0` | Cognito authorization code/PKCE, callback and token-session handling |
| lucide-react | `^1.57.0` | Consistent interface icons |
| HTML and CSS | Browser standards; project styles/tokens | Responsive layout, entry page, accessibility and reduced-motion behavior |
| JSON / NDJSON / gzip | Schema version 1; standard Python libraries | API messages, CloudFormation templates and compressed archive files |
| SQL | Athena workgroup queries | Deduplicated date/motor aggregates with predefined expressions |

Node.js is a build/test tool, not the deployed application server. The local authoring machine reports Node v22.14.0. AWS serves the built static files; Lambda runs the Python API. No frontend process needs to stay running on the developer's computer for the deployment to work.

## 3.3 Testing, validation and engineering tools

| Tool | Recorded manifest/lock version | Use |
| --- | --- | --- |
| pytest | Lock 8.4.2 | Backend, simulator, CLI audit, infrastructure and live AWS test orchestration |
| Moto | Lock 5.2.4 | Controlled AWS handler integration tests without changing live infrastructure |
| cfn-lint | Lock 1.57.2 | CloudFormation resource/schema validation for the chosen region |
| CloudFormation Guard | Version 3 tool family | Project infrastructure security/configuration assertions across the three templates |
| Ruff | Lock 0.17.0 | Python linting, import and correctness checks |
| Playwright Test | `^1.64.1` | Controlled Chromium UI cases and real hosted Cognito/deployed dashboard journeys |
| axe-core Playwright integration | `^4.13.0` | Automated accessibility checks on tested views |
| Prettier | `^3.9.10` | Frontend source formatting |
| Git | Installed local CLI | Incremental source/evidence/documentation commits and reviewable history |
| PowerShell | Windows shell | Development and CLI/script orchestration |
| SHA-256 hashing | Python standard library | Event/batch identity and served-release integrity comparisons |

Git and the AWS CLI are operational prerequisites; their exact installation versions were not pinned in the project manifests. This report does not invent those values. AWS CLI executable: `C:\Users\aksha\AppData\Local\Programs\Amazon\AWSCLIV2\aws.exe`.

Codex assisted implementation, testing and documentation. The frontend-design skill was used for the revised minimal entry page. These are authoring aids, not deployed AWS services or runtime dependencies. Assignment diagrams are generated vector drawings with matching editable Mermaid text. ReportLab creates the PDF, Pillow supports visual QA, and pdfplumber/pypdfium2 verify text/pages and render review images; these document-generation tools are separate from project application dependencies.

## 3.4 Source map and reproducibility

| Repository location | Responsibility |
| --- | --- |
| `PRD.md` | Original functional scope and approved operating constraints |
| `backend/domain.py` | Validation, canonical hashing, fault counters and predefined SQL |
| `backend/ingestion.py` | Signed ingestion handler and queue envelope |
| `backend/processor.py` | Archive, event deduplication, transactional state and alert transitions |
| `backend/api.py` | Human routes, roles, readings, controls, users and report coordination |
| `backend/notifications.py` | Subscription awareness and durable pending notification publication |
| `backend/aws_support.py` | Reused SDK clients, bounded retries, serialization and response helpers |
| `simulator/main.py` | Smooth synthetic readings, signed batching, remote controls and acknowledgements |
| `infra/generate.py`, generated JSON and `security.guard` | Infrastructure source, deployable templates and policy assertions |
| `scripts/aws_cli.py` and `AWS_COMMANDS.txt` | Logged operator CLI execution and immutable append history |
| `scripts/deploy.py`, `package.py`, `update_simulator.py` | Reproducible release/deployment workflow |
| `scripts/publish_frontend.py` | Independent static release and CloudFront invalidation |
| `scripts/recovery.py` | Separate-table bounded reconstruction with no SNS publication |
| `scripts/budget_model.py`, `cost_estimate.py` | Cost estimate calculations and captured pricing inputs |
| `tests/` and `tests/live/` | Controlled backend checks and actual AWS acceptance scenarios |
| `frontend/src/` and `frontend/tests/` | React application and controlled/deployed browser scenarios |
| `docs/` | API contract, resource outputs, recorded XML/JSON, screenshots and shutdown runbook |
| `assignment_docs/` | This submission report, source write-ups, diagrams and selected evidence |

For project execution, follow the repository README rather than treating the report as a list of commands already run. Typical validation includes `python -m scripts.validate`, `pytest` and the frontend's `npm run build` / `npm test` scripts; live tests must follow their explicit opt-in/environment requirements. New AWS CLI calls must use the logger, verify the authorized account/region and respect continued operation. Rebuilding these submission documents does not perform AWS operations.

## 3.5 References

Implementation facts are grounded in the repository files listed above, the current PRD and recorded evidence. AWS documentation links below explain the underlying service behavior; they are not evidence that an unrecorded deployment/test happened.

- AWS Lambda with SQS: https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html
- SQS partial batch responses: https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html
- DynamoDB transactions: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transactions.html
- DynamoDB TTL behavior: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html
- CloudFront private S3 origin access: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html
- Cognito authorization endpoint/PKCE: https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html
- Cognito email settings: https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-email.html
- Cognito password-reset error behavior: https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pool-managing-errors.html
- Athena workgroup scan limits: https://docs.aws.amazon.com/athena/latest/ug/workgroups-setting-control-limits-cloudwatch.html
- Athena partition projection: https://docs.aws.amazon.com/athena/latest/ug/partition-projection.html

The pinned manifests and local source remain the authority for this implementation. Future service/library changes may require revalidation.
