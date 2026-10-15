"""Generate plain CloudFormation JSON. Commit generated templates for review."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def ref(name):
    return {"Ref": name}


def sub(value, variables=None):
    return {"Fn::Sub": [value, variables]} if variables else {"Fn::Sub": value}


def att(name, attribute="Arn"):
    return {"Fn::GetAtt": [name, attribute]}


def template(description):
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": description,
        "Metadata": {"AWSToolsMetrics": {"AWSAgentToolkit": "aws-cloudformation@3"}},
        "Resources": {},
        "Outputs": {},
    }


def add(t, name, kind, properties, why, must=(), **options):
    t["Resources"][name] = {
        "Type": "AWS::" + kind,
        "Properties": properties,
        "Metadata": {"com.aws.cloudformation.Context": {"why": why, "must": list(must)}},
        **options,
    }


def bucket(t, name, why, days=30):
    add(
        t,
        name,
        "S3::Bucket",
        {
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            },
            "VersioningConfiguration": {"Status": "Enabled"},
            "PublicAccessBlockConfiguration": {
                key: True
                for key in (
                    "BlockPublicAcls",
                    "BlockPublicPolicy",
                    "IgnorePublicAcls",
                    "RestrictPublicBuckets",
                )
            },
            "OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
            "LifecycleConfiguration": {
                "Rules": [
                    {
                        "Id": "Retention",
                        "Status": "Enabled",
                        "ExpirationInDays": days,
                        "NoncurrentVersionExpiration": {"NoncurrentDays": days},
                        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
                    },
                    {"Id": "DeleteMarkers", "Status": "Enabled", "ExpiredObjectDeleteMarker": True},
                ]
            },
            "Tags": [{"Key": "Project", "Value": "ccproj"}],
        },
        why,
        ["Keep private, encrypted, versioned; bound current/noncurrent retention"],
        DeletionPolicy="RetainExceptOnCreate",
        UpdateReplacePolicy="Retain",
    )
    add(
        t,
        name + "Policy",
        "S3::BucketPolicy",
        {
            "Bucket": ref(name),
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "TLSOnly",
                        "Effect": "Deny",
                        "Principal": "*",
                        "Action": "s3:*",
                        "Resource": [att(name), sub("${BucketArn}/*", {"BucketArn": att(name)})],
                        "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                    }
                ],
            },
        },
        "Require encrypted transport",
        ["Preserve TLS deny"],
    )


def statement(actions, resources):
    return {"Effect": "Allow", "Action": actions, "Resource": resources}


def role(t, name, service, permissions, why):
    add(
        t,
        name,
        "IAM::Role",
        {
            "AssumeRolePolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": service},
                        "Action": "sts:AssumeRole",
                    }
                ],
            },
            "Policies": [
                {
                    "PolicyName": "ScopedAccess",
                    "PolicyDocument": {"Version": "2012-10-17", "Statement": permissions},
                }
            ],
        },
        why,
        ["Only enumerated application access; no user access keys"],
    )


def log_permissions(function):
    return statement(
        ["logs:CreateLogStream", "logs:PutLogEvents"],
        sub(
            "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/${AWS::StackName}-"
            + function
            + ":*"
        ),
    )


def function(t, name, handler, permissions, environment, why, timeout=30):
    role(t, name + "Role", "lambda.amazonaws.com", [log_permissions(name), *permissions], why)
    add(
        t,
        name + "Logs",
        "Logs::LogGroup",
        {"LogGroupName": sub("/aws/lambda/${AWS::StackName}-" + name), "RetentionInDays": 7},
        "Bound diagnostic retention",
    )
    add(
        t,
        name,
        "Lambda::Function",
        {
            "FunctionName": sub("${AWS::StackName}-" + name),
            "Runtime": "python3.12",
            "Architectures": ["arm64"],
            "Handler": handler,
            "Role": att(name + "Role"),
            "Code": {"S3Bucket": ref("ArtifactBucket"), "S3Key": ref("BackendKey")},
            "Timeout": timeout,
            "MemorySize": 256,
            "Environment": {"Variables": environment},
            "Tags": [{"Key": "Project", "Value": "ccproj"}],
        },
        why,
        ["Role credentials only; no public function URL"],
        DependsOn=[name + "Logs"],
    )


def build():
    bootstrap = template(
        "Deployment artifacts kept private and versioned for reproducible industrial monitoring releases"
    )
    bucket(bootstrap, "Artifacts", "Versioned backend and simulator release packages", 90)
    bootstrap["Outputs"]["ArtifactBucket"] = {"Value": ref("Artifacts")}

    t = template(
        "Industrial motor monitoring with queued retry-safe telemetry, protected APIs, and private frontend delivery"
    )
    t["Parameters"] = {
        "ArtifactBucket": {"Type": "String"},
        "BackendKey": {"Type": "String"},
        "AlertEmail": {"Type": "String", "Default": "collegeproject@akshaykripalani.com"},
        "BudgetStart": {
            "Type": "String",
            "Description": "Unix epoch when project budget tracking begins",
        },
        "BudgetEnd": {
            "Type": "String",
            "Description": "Unix epoch: fixed project budget period end",
        },
    }
    bucket(t, "Archive", "Batched date-partitioned history, retained for recovery exercises")
    bucket(t, "Results", "Private bounded Athena query results", 7)
    bucket(t, "Frontend", "Private browser assets delivered only through CloudFront", 365)
    for name in ("Data", "Controls"):
        props = {
            "BillingMode": "PAY_PER_REQUEST",
            "AttributeDefinitions": [
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            "KeySchema": [
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            "SSESpecification": {"SSEEnabled": True},
            "TimeToLiveSpecification": {"AttributeName": "expiresAt", "Enabled": True},
            "Tags": [{"Key": "Project", "Value": "ccproj"}],
        }
        if name == "Data":
            props["AttributeDefinitions"] += [
                {"AttributeName": "workStatus", "AttributeType": "S"},
                {"AttributeName": "workAt", "AttributeType": "S"},
            ]
            props["GlobalSecondaryIndexes"] = [
                {
                    "IndexName": "Work",
                    "KeySchema": [
                        {"AttributeName": "workStatus", "KeyType": "HASH"},
                        {"AttributeName": "workAt", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ]
        add(
            t,
            name,
            "DynamoDB::Table",
            props,
            "Live state/history and notification intent"
            if name == "Data"
            else "Requested/applied simulator modes separate from measurements",
            ["No destructive replacement without data export"],
            DeletionPolicy="RetainExceptOnCreate",
            UpdateReplacePolicy="Retain",
        )
    add(
        t,
        "DeadLetter",
        "SQS::Queue",
        {"FifoQueue": True, "MessageRetentionPeriod": 1209600, "SqsManagedSseEnabled": True},
        "Isolate repeatedly failing envelopes for inspection and redrive",
        ["FIFO matches telemetry source"],
    )
    add(
        t,
        "Telemetry",
        "SQS::Queue",
        {
            "FifoQueue": True,
            "ContentBasedDeduplication": False,
            "VisibilityTimeout": 180,
            "MessageRetentionPeriod": 345600,
            "SqsManagedSseEnabled": True,
            "RedrivePolicy": {"deadLetterTargetArn": att("DeadLetter"), "maxReceiveCount": 3},
        },
        "Ordered factory arrivals simplify consecutive-reading rules",
        [
            "Visibility >= 6 * processor timeout",
            "DynamoDB handles duplicates outside SQS dedup window",
        ],
    )
    for queue in ("Telemetry", "DeadLetter"):
        add(
            t,
            queue + "Policy",
            "SQS::QueuePolicy",
            {
                "Queues": [ref(queue)],
                "PolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Deny",
                            "Principal": "*",
                            "Action": "sqs:*",
                            "Resource": att(queue),
                            "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                        }
                    ],
                },
            },
            "Reject non-TLS traffic for this queue",
            ["SQS requires one queue resource per policy statement"],
        )
    add(
        t,
        "NotificationKey",
        "KMS::Key",
        {
            "Description": "Encrypt motor and operational SNS notifications",
            "EnableKeyRotation": True,
            "KeyPolicy": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "AccountAdmin",
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": sub("arn:${AWS::Partition}:iam::${AWS::AccountId}:root")
                        },
                        "Action": "kms:*",
                        "Resource": "*",
                    },
                    {
                        "Sid": "Alarms",
                        "Effect": "Allow",
                        "Principal": {"Service": "cloudwatch.amazonaws.com"},
                        "Action": ["kms:Decrypt", "kms:GenerateDataKey*"],
                        "Resource": "*",
                        "Condition": {
                            "StringEquals": {"aws:SourceAccount": ref("AWS::AccountId")},
                            "ArnLike": {
                                "aws:SourceArn": sub(
                                    "arn:${AWS::Partition}:cloudwatch:${AWS::Region}:${AWS::AccountId}:alarm:${AWS::StackName}-*"
                                )
                            },
                        },
                    },
                ],
            },
        },
        "SNS encryption key permits alarm delivery without a broad managed SNS policy",
        ["Only same-account project alarms may use service principal"],
        DeletionPolicy="RetainExceptOnCreate",
        UpdateReplacePolicy="Retain",
    )
    add(
        t,
        "Alerts",
        "SNS::Topic",
        {"KmsMasterKeyId": ref("NotificationKey"), "Tags": [{"Key": "Project", "Value": "ccproj"}]},
        "Equipment and operational email notifications",
    )
    add(
        t,
        "AlertSubscription",
        "SNS::Subscription",
        {"TopicArn": ref("Alerts"), "Protocol": "email", "Endpoint": ref("AlertEmail")},
        "User-selected alert recipient",
        ["Delivery pending until recipient confirms"],
    )
    add(
        t,
        "AlertPolicy",
        "SNS::TopicPolicy",
        {
            "Topics": [ref("Alerts")],
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "cloudwatch.amazonaws.com"},
                        "Action": "sns:Publish",
                        "Resource": ref("Alerts"),
                        "Condition": {
                            "StringEquals": {"aws:SourceAccount": ref("AWS::AccountId")},
                            "ArnLike": {
                                "aws:SourceArn": sub(
                                    "arn:${AWS::Partition}:cloudwatch:${AWS::Region}:${AWS::AccountId}:alarm:${AWS::StackName}-*"
                                )
                            },
                        },
                    }
                ],
            },
        },
        "Permit only this project's alarms to publish",
    )
    add(
        t,
        "Pool",
        "Cognito::UserPool",
        {
            "UserPoolName": sub("${AWS::StackName}-users"),
            "UserPoolTier": "LITE",
            "UsernameAttributes": ["email"],
            "AutoVerifiedAttributes": ["email"],
            "AdminCreateUserConfig": {"AllowAdminCreateUserOnly": True},
            "Policies": {
                "PasswordPolicy": {
                    "MinimumLength": 12,
                    "RequireLowercase": True,
                    "RequireUppercase": True,
                    "RequireNumbers": True,
                    "RequireSymbols": True,
                    "TemporaryPasswordValidityDays": 7,
                }
            },
            "AccountRecoverySetting": {
                "RecoveryMechanisms": [{"Name": "verified_email", "Priority": 1}]
            },
            "UserPoolTags": {"Project": "ccproj"},
        },
        "Small invited user directory with classic hosted login",
        ["No public registration; do not replace pool casually"],
        DeletionPolicy="RetainExceptOnCreate",
        UpdateReplacePolicy="Retain",
    )
    for name in ("viewer", "operator"):
        add(
            t,
            name.title() + "Group",
            "Cognito::UserPoolGroup",
            {"GroupName": name, "UserPoolId": ref("Pool")},
            "Application authorization role",
        )
    add(
        t,
        "OriginAccess",
        "CloudFront::OriginAccessControl",
        {
            "OriginAccessControlConfig": {
                "Name": sub("${AWS::StackName}-origin"),
                "OriginAccessControlOriginType": "s3",
                "SigningBehavior": "always",
                "SigningProtocol": "sigv4",
            }
        },
        "Signed access to private frontend bucket",
    )
    add(
        t,
        "SecurityHeaders",
        "CloudFront::ResponseHeadersPolicy",
        {
            "ResponseHeadersPolicyConfig": {
                "Name": sub("${AWS::StackName}-headers"),
                "SecurityHeadersConfig": {
                    "ContentTypeOptions": {"Override": True},
                    "FrameOptions": {"FrameOption": "DENY", "Override": True},
                    "ReferrerPolicy": {
                        "ReferrerPolicy": "strict-origin-when-cross-origin",
                        "Override": True,
                    },
                    "StrictTransportSecurity": {
                        "AccessControlMaxAgeSec": 31536000,
                        "IncludeSubdomains": True,
                        "Override": True,
                    },
                    "ContentSecurityPolicy": {
                        "ContentSecurityPolicy": "default-src 'self'; script-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://*.amazonaws.com https://*.amazoncognito.com; frame-ancestors 'none'; base-uri 'self'; object-src 'none'",
                        "Override": True,
                    },
                },
            }
        },
        "React security headers; chart library needs inline layout attributes only, scripts and style elements stay self-hosted",
        [
            "No inline scripts or external style elements",
            "Inline style attributes only for responsive chart layout",
        ],
    )
    add(
        t,
        "Distribution",
        "CloudFront::Distribution",
        {
            "DistributionConfig": {
                "Enabled": True,
                "DefaultRootObject": "index.html",
                "PriceClass": "PriceClass_200",
                "HttpVersion": "http2and3",
                "Origins": [
                    {
                        "Id": "frontend",
                        "DomainName": att("Frontend", "RegionalDomainName"),
                        "OriginAccessControlId": ref("OriginAccess"),
                        "S3OriginConfig": {"OriginAccessIdentity": ""},
                    }
                ],
                "DefaultCacheBehavior": {
                    "TargetOriginId": "frontend",
                    "ViewerProtocolPolicy": "redirect-to-https",
                    "AllowedMethods": ["GET", "HEAD", "OPTIONS"],
                    "CachedMethods": ["GET", "HEAD"],
                    "Compress": True,
                    "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",
                    "ResponseHeadersPolicyId": ref("SecurityHeaders"),
                },
                "ViewerCertificate": {"CloudFrontDefaultCertificate": True},
                "CustomErrorResponses": [
                    {
                        "ErrorCode": 403,
                        "ResponseCode": 200,
                        "ResponsePagePath": "/index.html",
                        "ErrorCachingMinTTL": 0,
                    },
                    {
                        "ErrorCode": 404,
                        "ResponseCode": 200,
                        "ResponsePagePath": "/index.html",
                        "ErrorCachingMinTTL": 0,
                    },
                ],
            },
            "Tags": [{"Key": "Project", "Value": "ccproj"}],
        },
        "HTTPS static frontend using private S3 origin",
        ["Never make S3 website public"],
    )
    t["Resources"]["FrontendPolicy"]["Properties"]["PolicyDocument"]["Statement"].append(
        {
            "Effect": "Allow",
            "Principal": {"Service": "cloudfront.amazonaws.com"},
            "Action": "s3:GetObject",
            "Resource": sub("${Frontend.Arn}/*"),
            "Condition": {
                "StringEquals": {
                    "AWS:SourceArn": sub(
                        "arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/${Distribution}"
                    )
                }
            },
        }
    )
    add(
        t,
        "BrowserClient",
        "Cognito::UserPoolClient",
        {
            "UserPoolId": ref("Pool"),
            "ClientName": "dashboard",
            "GenerateSecret": False,
            "AllowedOAuthFlowsUserPoolClient": True,
            "AllowedOAuthFlows": ["code"],
            "AllowedOAuthScopes": ["openid", "email", "profile"],
            "SupportedIdentityProviders": ["COGNITO"],
            "CallbackURLs": [
                sub("https://${Distribution.DomainName}/callback"),
                "http://localhost:5173/callback",
            ],
            "LogoutURLs": [sub("https://${Distribution.DomainName}/"), "http://localhost:5173/"],
            "ExplicitAuthFlows": ["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_ADMIN_USER_PASSWORD_AUTH"],
            "AccessTokenValidity": 10,
            "IdTokenValidity": 10,
            "RefreshTokenValidity": 1,
            "TokenValidityUnits": {
                "AccessToken": "minutes",
                "IdToken": "minutes",
                "RefreshToken": "days",
            },
            "EnableTokenRevocation": True,
            "PreventUserExistenceErrors": "ENABLED",
        },
        "Public PKCE browser client; IAM-protected admin auth supports automated live tests",
        ["No browser secret; browser uses authorization code with PKCE"],
    )
    add(
        t,
        "PoolDomain",
        "Cognito::UserPoolDomain",
        {
            "Domain": sub("${AWS::StackName}-${AWS::AccountId}"),
            "UserPoolId": ref("Pool"),
            "ManagedLoginVersion": 1,
        },
        "Classic hosted login fits the Lite plan",
    )
    add(
        t,
        "Catalog",
        "Glue::Database",
        {
            "CatalogId": ref("AWS::AccountId"),
            "DatabaseInput": {
                "Name": sub(
                    "${DbName}",
                    {"DbName": {"Fn::Join": ["_", {"Fn::Split": ["-", ref("AWS::StackName")]}]}},
                )
            },
        },
        "Static telemetry schema without crawler cost",
    )
    columns = {
        "schemaversion": "int",
        "eventid": "string",
        "deviceid": "string",
        "observedat": "string",
        "receivedat": "string",
        "temperaturec": "double",
        "vibrationmms": "double",
        "powerwatts": "double",
        "operatingstate": "string",
    }
    add(
        t,
        "HistoryTable",
        "Glue::Table",
        {
            "CatalogId": ref("AWS::AccountId"),
            "DatabaseName": ref("Catalog"),
            "TableInput": {
                "Name": "telemetry",
                "TableType": "EXTERNAL_TABLE",
                "Parameters": {
                    "EXTERNAL": "TRUE",
                    "classification": "json",
                    "projection.enabled": "true",
                    "projection.day.type": "date",
                    "projection.day.format": "yyyy-MM-dd",
                    "projection.day.range": "2026-01-01,NOW",
                    "projection.day.interval": "1",
                    "projection.day.interval.unit": "DAYS",
                    "storage.location.template": sub("s3://${Archive}/telemetry/day=\u0024{day}/"),
                },
                "PartitionKeys": [{"Name": "day", "Type": "string"}],
                "StorageDescriptor": {
                    "Columns": [{"Name": k, "Type": v} for k, v in columns.items()],
                    "Location": sub("s3://${Archive}/telemetry/"),
                    "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
                    "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                    "SerdeInfo": {
                        "SerializationLibrary": "org.openx.data.jsonserde.JsonSerDe",
                        "Parameters": {"case.insensitive": "true"},
                    },
                },
            },
        },
        "Projected date partitions over compressed NDJSON",
        ["No unrestricted queries; preserve observed times and identities"],
    )
    # Escape Athena's projection placeholder through Fn::Sub's literal syntax.
    t["Resources"]["HistoryTable"]["Properties"]["TableInput"]["Parameters"][
        "storage.location.template"
    ] = sub("s3://${Archive}/telemetry/day=${!day}/")
    add(
        t,
        "Workgroup",
        "Athena::WorkGroup",
        {
            "Name": sub("${AWS::StackName}-reports"),
            "WorkGroupConfiguration": {
                "EnforceWorkGroupConfiguration": True,
                "PublishCloudWatchMetricsEnabled": False,
                "BytesScannedCutoffPerQuery": 10485760,
                "ResultConfiguration": {
                    "OutputLocation": sub("s3://${Results}/queries/"),
                    "EncryptionConfiguration": {"EncryptionOption": "SSE_S3"},
                },
            },
            "Tags": [{"Key": "Project", "Value": "ccproj"}],
        },
        "On-demand historical SQL with 10 MiB scan cutoff",
        ["No reserved capacity; results private"],
    )
    common = {
        "DATA_TABLE": ref("Data"),
        "CONTROL_TABLE": ref("Controls"),
        "ARCHIVE_BUCKET": ref("Archive"),
        "ALERT_TOPIC": ref("Alerts"),
        "USER_POOL": ref("Pool"),
        "GLUE_DATABASE": ref("Catalog"),
        "ATHENA_WORKGROUP": ref("Workgroup"),
        "OFFLINE_SECONDS": "60",
    }
    data_arn = att("Data")
    data_index = sub("${Data.Arn}/index/*")
    function(
        t,
        "Ingestion",
        "backend.ingestion.handler",
        [statement(["sqs:SendMessage"], att("Telemetry"))],
        {"QUEUE_URL": ref("Telemetry")},
        "Validate signed ingestion and accept only after SQS enqueue",
    )
    function(
        t,
        "Processor",
        "backend.processor.handler",
        [
            statement(
                ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"],
                att("Telemetry"),
            ),
            statement(["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"], data_arn),
            statement(["s3:PutObject"], sub("${Archive.Arn}/telemetry/*")),
        ],
        common,
        "Archive then atomically commit state/history/alert intent",
        timeout=30,
    )
    function(
        t,
        "Notifier",
        "backend.notifications.handler",
        [
            statement(["dynamodb:Query"], data_index),
            statement(["dynamodb:UpdateItem"], data_arn),
            statement(["sns:Publish", "sns:ListSubscriptionsByTopic"], ref("Alerts")),
            statement(["kms:Decrypt", "kms:GenerateDataKey"], att("NotificationKey")),
        ],
        {**common, "DASHBOARD_URL": sub("https://${Distribution.DomainName}")},
        "Retry durable intent; send readable fault emails with deployment-derived equipment links",
    )
    api_permissions = [
        statement(
            ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:PutItem", "dynamodb:UpdateItem"],
            [data_arn, att("Controls")],
        ),
        statement(
            [
                "cognito-idp:AdminGetUser",
                "cognito-idp:AdminListGroupsForUser",
                "cognito-idp:ListUsers",
                "cognito-idp:AdminCreateUser",
                "cognito-idp:AdminAddUserToGroup",
                "cognito-idp:AdminRemoveUserFromGroup",
            ],
            att("Pool"),
        ),
        statement(["sns:ListSubscriptionsByTopic"], ref("Alerts")),
        statement(
            ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults"],
            sub(
                "arn:${AWS::Partition}:athena:${AWS::Region}:${AWS::AccountId}:workgroup/${Workgroup}"
            ),
        ),
        statement(
            ["glue:GetDatabase", "glue:GetTable", "glue:GetPartitions"],
            [
                sub("arn:${AWS::Partition}:glue:${AWS::Region}:${AWS::AccountId}:catalog"),
                sub(
                    "arn:${AWS::Partition}:glue:${AWS::Region}:${AWS::AccountId}:database/${Catalog}"
                ),
                sub(
                    "arn:${AWS::Partition}:glue:${AWS::Region}:${AWS::AccountId}:table/${Catalog}/telemetry"
                ),
            ],
        ),
        statement(["s3:GetBucketLocation", "s3:ListBucket"], [att("Archive"), att("Results")]),
        statement(
            ["s3:GetObject"], [sub("${Archive.Arn}/telemetry/*"), sub("${Results.Arn}/queries/*")]
        ),
        statement(["s3:PutObject"], sub("${Results.Arn}/queries/*")),
    ]
    function(
        t,
        "ApiBackend",
        "backend.api.handler",
        api_permissions,
        common,
        "Dashboard queries, operator authorization, controls and bounded reports",
    )
    add(
        t,
        "ProcessingMapping",
        "Lambda::EventSourceMapping",
        {
            "EventSourceArn": att("Telemetry"),
            "FunctionName": ref("Processor"),
            "BatchSize": 10,
            "FunctionResponseTypes": ["ReportBatchItemFailures"],
            "Enabled": True,
        },
        "Native FIFO consumer with partial failure response",
    )
    add(
        t,
        "ScheduleGroup",
        "Scheduler::ScheduleGroup",
        {"Name": sub("${AWS::StackName}-jobs")},
        "Scope scheduled notification jobs",
    )
    role(
        t,
        "ScheduleRole",
        "scheduler.amazonaws.com",
        [statement(["lambda:InvokeFunction"], att("Notifier"))],
        "Only notification invocation from this schedule group",
    )
    t["Resources"]["ScheduleRole"]["Properties"]["AssumeRolePolicyDocument"]["Statement"][0][
        "Condition"
    ] = {
        "StringEquals": {
            "aws:SourceAccount": ref("AWS::AccountId"),
            "aws:SourceArn": att("ScheduleGroup"),
        }
    }
    add(
        t,
        "NotificationSchedule",
        "Scheduler::Schedule",
        {
            "GroupName": ref("ScheduleGroup"),
            "FlexibleTimeWindow": {"Mode": "OFF"},
            "ScheduleExpression": "rate(1 minute)",
            "State": "ENABLED",
            "Target": {
                "Arn": att("Notifier"),
                "RoleArn": att("ScheduleRole"),
                "Input": "{}",
                "RetryPolicy": {"MaximumRetryAttempts": 2, "MaximumEventAgeInSeconds": 120},
            },
        },
        "Periodic durable outbox drain through EventBridge Scheduler",
    )
    add(
        t,
        "HttpApi",
        "ApiGatewayV2::Api",
        {
            "Name": sub("${AWS::StackName}-http"),
            "ProtocolType": "HTTP",
            "CorsConfiguration": {
                "AllowOrigins": [
                    sub("https://${Distribution.DomainName}"),
                    "http://localhost:5173",
                ],
                "AllowHeaders": [
                    "content-type",
                    "authorization",
                    "x-amz-date",
                    "x-amz-security-token",
                    "x-amz-content-sha256",
                ],
                "AllowMethods": ["GET", "POST", "PUT", "OPTIONS"],
                "MaxAge": 300,
            },
        },
        "Low-cost HTTP API with separate IAM and JWT route authentication",
    )
    add(
        t,
        "ApiLogs",
        "Logs::LogGroup",
        {"RetentionInDays": 7},
        "Bounded access logs without tokens or request bodies",
    )
    add(
        t,
        "ApiStage",
        "ApiGatewayV2::Stage",
        {
            "ApiId": ref("HttpApi"),
            "StageName": "$default",
            "AutoDeploy": True,
            "DefaultRouteSettings": {"ThrottlingBurstLimit": 20, "ThrottlingRateLimit": 10},
            "AccessLogSettings": {
                "DestinationArn": att("ApiLogs"),
                "Format": '{"requestId":"$context.requestId","route":"$context.routeKey","status":"$context.status","latency":"$context.responseLatency"}',
            },
        },
        "Throttle demo usage and retain request outcomes",
    )
    add(
        t,
        "Jwt",
        "ApiGatewayV2::Authorizer",
        {
            "ApiId": ref("HttpApi"),
            "Name": "Cognito",
            "AuthorizerType": "JWT",
            "IdentitySource": ["$request.header.Authorization"],
            "JwtConfiguration": {
                "Issuer": sub("https://cognito-idp.${AWS::Region}.amazonaws.com/${Pool}"),
                "Audience": [ref("BrowserClient")],
            },
        },
        "Cognito access-token authorization",
    )
    for name, function_name in (("Ingest", "Ingestion"), ("Dashboard", "ApiBackend")):
        add(
            t,
            name + "Integration",
            "ApiGatewayV2::Integration",
            {
                "ApiId": ref("HttpApi"),
                "IntegrationType": "AWS_PROXY",
                "IntegrationUri": att(function_name),
                "PayloadFormatVersion": "2.0",
            },
            "Lambda HTTP proxy",
        )
        add(
            t,
            name + "Permission",
            "Lambda::Permission",
            {
                "FunctionName": ref(function_name),
                "Action": "lambda:InvokeFunction",
                "Principal": "apigateway.amazonaws.com",
                "SourceArn": sub(
                    "arn:${AWS::Partition}:execute-api:${AWS::Region}:${AWS::AccountId}:${HttpApi}/*"
                ),
                "SourceAccount": ref("AWS::AccountId"),
            },
            "Only this API can invoke handler",
        )
    add(
        t,
        "TelemetryRoute",
        "ApiGatewayV2::Route",
        {
            "ApiId": ref("HttpApi"),
            "RouteKey": "POST /telemetry",
            "AuthorizationType": "AWS_IAM",
            "Target": sub("integrations/${IngestIntegration}"),
        },
        "IAM signed simulator ingress",
    )
    routes = [
        "GET /devices",
        "GET /devices/{deviceId}",
        "GET /devices/{deviceId}/readings",
        "GET /alerts",
        "POST /controls/{deviceId}",
        "POST /controls/reset-all",
        "POST /reports",
        "GET /reports/{reportId}",
        "GET /users",
        "POST /users",
        "PUT /users",
    ]
    for index, route_name in enumerate(routes):
        add(
            t,
            f"Route{index}",
            "ApiGatewayV2::Route",
            {
                "ApiId": ref("HttpApi"),
                "RouteKey": route_name,
                "AuthorizationType": "JWT",
                "AuthorizerId": ref("Jwt"),
                "AuthorizationScopes": ["openid", "aws.cognito.signin.user.admin"],
                "Target": sub("integrations/${DashboardIntegration}"),
            },
            "Protected application endpoint",
            ["Access-token scopes required; backend enforces viewer/operator roles"],
        )
    alarms = [
        (
            "Backlog",
            "AWS/SQS",
            "ApproximateAgeOfOldestMessage",
            [{"Name": "QueueName", "Value": att("Telemetry", "QueueName")}],
            120,
        ),
        (
            "DLQ",
            "AWS/SQS",
            "ApproximateNumberOfMessagesVisible",
            [{"Name": "QueueName", "Value": att("DeadLetter", "QueueName")}],
            1,
        ),
    ]
    for func in ("Ingestion", "Processor", "Notifier", "ApiBackend"):
        alarms += [
            (
                func + "Errors",
                "AWS/Lambda",
                "Errors",
                [{"Name": "FunctionName", "Value": ref(func)}],
                1,
            ),
            (
                func + "Throttles",
                "AWS/Lambda",
                "Throttles",
                [{"Name": "FunctionName", "Value": ref(func)}],
                1,
            ),
        ]
    for name, namespace, metric, dimensions, threshold in alarms:
        add(
            t,
            name + "Alarm",
            "CloudWatch::Alarm",
            {
                "AlarmName": sub("${AWS::StackName}-" + name),
                "Namespace": namespace,
                "MetricName": metric,
                "Dimensions": dimensions,
                "Statistic": "Maximum" if namespace == "AWS/SQS" else "Sum",
                "Period": 60,
                "EvaluationPeriods": 1,
                "Threshold": threshold,
                "ComparisonOperator": "GreaterThanOrEqualToThreshold",
                "TreatMissingData": "notBreaching",
                "AlarmActions": [ref("Alerts")],
            },
            "Small operational alarm set",
        )
    add(
        t,
        "ProjectBudget",
        "Budgets::Budget",
        {
            "Budget": {
                "BudgetName": sub("${AWS::StackName}-total-ceiling"),
                "BudgetType": "COST",
                "TimeUnit": "CUSTOM",
                "TimePeriod": {"Start": ref("BudgetStart"), "End": ref("BudgetEnd")},
                "BudgetLimit": {"Amount": 50, "Unit": "USD"},
                "CostTypes": {
                    "IncludeCredit": False,
                    "IncludeRefund": False,
                    "IncludeTax": True,
                    "UseBlended": False,
                },
            },
            "NotificationsWithSubscribers": [
                {
                    "Notification": {
                        "NotificationType": "ACTUAL",
                        "ComparisonOperator": "GREATER_THAN",
                        "Threshold": threshold,
                        "ThresholdType": "ABSOLUTE_VALUE",
                    },
                    "Subscribers": [{"SubscriptionType": "EMAIL", "Address": ref("AlertEmail")}],
                }
                for threshold in (20, 30, 40)
            ],
        },
        "Conservative account-wide spending budget for project period before credits; notify at user-selected amounts",
        [
            "No automatic stop or teardown",
            "Account-wide budget also counts teammate usage; avoids omissions from unactivated tags; alerts are delayed",
        ],
    )
    outputs = {
        "ApiUrl": att("HttpApi", "ApiEndpoint"),
        "DataTable": ref("Data"),
        "ControlTable": ref("Controls"),
        "QueueUrl": ref("Telemetry"),
        "QueueArn": att("Telemetry"),
        "DlqUrl": ref("DeadLetter"),
        "DlqArn": att("DeadLetter"),
        "ArchiveBucket": ref("Archive"),
        "ResultsBucket": ref("Results"),
        "FrontendBucket": ref("Frontend"),
        "DistributionId": ref("Distribution"),
        "DashboardUrl": sub("https://${Distribution.DomainName}"),
        "UserPoolId": ref("Pool"),
        "ClientId": ref("BrowserClient"),
        "LoginDomain": sub("https://${PoolDomain}.auth.${AWS::Region}.amazoncognito.com"),
        "AlertTopicArn": ref("Alerts"),
        "GlueDatabase": ref("Catalog"),
        "AthenaWorkgroup": ref("Workgroup"),
        "ProcessorFunction": ref("Processor"),
        "NotifierFunction": ref("Notifier"),
        "ProcessingMapping": ref("ProcessingMapping"),
    }
    t["Outputs"] = {key: {"Value": value} for key, value in outputs.items()}

    ec2 = template(
        "Single three-motor factory simulator with IAM-only access and no inbound network ports or NAT gateway"
    )
    ec2["Parameters"] = {
        "ArtifactBucket": {"Type": "String"},
        "SimulatorKey": {"Type": "String"},
        "ApiUrl": {"Type": "String"},
        "ControlTable": {"Type": "String"},
        "ApiId": {"Type": "String"},
        "InstanceType": {
            "Type": "String",
            "Default": "t4g.micro",
            "AllowedValues": ["t4g.micro", "t4g.small"],
        },
        "Ami": {
            "Type": "AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>",
            "Default": "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64",
        },
    }
    add(
        ec2,
        "Vpc",
        "EC2::VPC",
        {
            "CidrBlock": "10.42.0.0/24",
            "EnableDnsSupport": True,
            "EnableDnsHostnames": True,
            "Tags": [{"Key": "Project", "Value": "ccproj"}],
        },
        "Explicit simulator network",
    )
    add(
        ec2,
        "Subnet",
        "EC2::Subnet",
        {"VpcId": ref("Vpc"), "CidrBlock": "10.42.0.0/26", "MapPublicIpOnLaunch": True},
        "Public subnet avoids hourly NAT charges",
    )
    add(ec2, "Gateway", "EC2::InternetGateway", {}, "HTTPS egress to AWS service endpoints")
    add(
        ec2,
        "AttachGateway",
        "EC2::VPCGatewayAttachment",
        {"VpcId": ref("Vpc"), "InternetGatewayId": ref("Gateway")},
        "Attach egress route",
    )
    add(ec2, "RouteTable", "EC2::RouteTable", {"VpcId": ref("Vpc")}, "Explicit internet routing")
    add(
        ec2,
        "InternetRoute",
        "EC2::Route",
        {
            "RouteTableId": ref("RouteTable"),
            "DestinationCidrBlock": "0.0.0.0/0",
            "GatewayId": ref("Gateway"),
        },
        "Outbound connectivity only",
        DependsOn=["AttachGateway"],
    )
    add(
        ec2,
        "SubnetRoute",
        "EC2::SubnetRouteTableAssociation",
        {"SubnetId": ref("Subnet"), "RouteTableId": ref("RouteTable")},
        "Bind public routing",
    )
    add(
        ec2,
        "SecurityGroup",
        "EC2::SecurityGroup",
        {
            "GroupDescription": "No inbound access; HTTPS and DNS egress",
            "VpcId": ref("Vpc"),
            "SecurityGroupEgress": [
                {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "CidrIp": "0.0.0.0/0"},
                {"IpProtocol": "udp", "FromPort": 53, "ToPort": 53, "CidrIp": "10.42.0.2/32"},
                {"IpProtocol": "tcp", "FromPort": 53, "ToPort": 53, "CidrIp": "10.42.0.2/32"},
            ],
        },
        "No SSH or other inbound ports; allow service HTTPS",
        ["Never add public ingress"],
    )
    role(
        ec2,
        "SimulatorRole",
        "ec2.amazonaws.com",
        [
            statement(
                ["execute-api:Invoke"],
                sub(
                    "arn:${AWS::Partition}:execute-api:${AWS::Region}:${AWS::AccountId}:${ApiId}/*/POST/telemetry"
                ),
            ),
            statement(
                ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"],
                sub(
                    "arn:${AWS::Partition}:dynamodb:${AWS::Region}:${AWS::AccountId}:table/${ControlTable}"
                ),
            ),
            statement(
                ["s3:GetObject"],
                sub("arn:${AWS::Partition}:s3:::${ArtifactBucket}/${SimulatorKey}"),
            ),
            statement(
                [
                    "ssm:UpdateInstanceInformation",
                    "ssmmessages:CreateControlChannel",
                    "ssmmessages:CreateDataChannel",
                    "ssmmessages:OpenControlChannel",
                    "ssmmessages:OpenDataChannel",
                ],
                "*",
            ),
            statement(
                [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:DescribeLogStreams",
                    "logs:PutLogEvents",
                ],
                sub(
                    "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:${AWS::StackName}-simulator:*"
                ),
            ),
        ],
        "Instance role signs ingestion, polls only controls, and reads exact release",
    )
    add(
        ec2,
        "Profile",
        "IAM::InstanceProfile",
        {"Roles": [ref("SimulatorRole")]},
        "Attach runtime role without access keys",
    )
    add(
        ec2,
        "SimulatorLogs",
        "Logs::LogGroup",
        {"LogGroupName": sub("${AWS::StackName}-simulator"), "RetentionInDays": 7},
        "Bounded simulator diagnostics",
    )
    userdata = """#!/bin/bash
set -euo pipefail
exec > >(tee /var/log/ccproj-bootstrap.log) 2>&1
dnf install -y python3.12 python3.12-pip amazon-cloudwatch-agent
mkdir -p /opt/ccproj
aws s3 cp 's3://${ArtifactBucket}/${SimulatorKey}' /tmp/simulator.tar.gz --region '${AWS::Region}'
tar -xzf /tmp/simulator.tar.gz -C /opt/ccproj
python3.12 -m venv /opt/ccproj/venv
/opt/ccproj/venv/bin/pip install --no-index --find-links /opt/ccproj/wheels -r /opt/ccproj/requirements-runtime.txt
useradd --system --home-dir /opt/ccproj ccproj
chown -R ccproj:ccproj /opt/ccproj
cat > /etc/systemd/system/ccproj-simulator.service <<'UNIT'
[Unit]
Description=Industrial motor simulator
After=network-online.target
Wants=network-online.target
[Service]
User=ccproj
WorkingDirectory=/opt/ccproj
Environment=API_URL=${ApiUrl}
Environment=CONTROL_TABLE=${ControlTable}
Environment=AWS_DEFAULT_REGION=${AWS::Region}
ExecStart=/opt/ccproj/venv/bin/python -m simulator.main
Restart=always
RestartSec=10
StandardOutput=append:/var/log/ccproj-simulator.log
StandardError=append:/var/log/ccproj-simulator.log
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
[Install]
WantedBy=multi-user.target
UNIT
touch /var/log/ccproj-simulator.log
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<'AGENT'
{"logs":{"logs_collected":{"files":{"collect_list":[{"file_path":"/var/log/ccproj-simulator.log","log_group_name":"${AWS::StackName}-simulator","log_stream_name":"{instance_id}","timezone":"UTC"},{"file_path":"/var/log/ccproj-bootstrap.log","log_group_name":"${AWS::StackName}-simulator","log_stream_name":"{instance_id}-bootstrap","timezone":"UTC"}]}}}}
AGENT
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
systemctl daemon-reload
systemctl enable --now ccproj-simulator
"""
    add(
        ec2,
        "Instance",
        "EC2::Instance",
        {
            "ImageId": ref("Ami"),
            "InstanceType": ref("InstanceType"),
            "IamInstanceProfile": ref("Profile"),
            "SubnetId": ref("Subnet"),
            "SecurityGroupIds": [ref("SecurityGroup")],
            "MetadataOptions": {
                "HttpTokens": "required",
                "HttpEndpoint": "enabled",
                "HttpPutResponseHopLimit": 1,
            },
            "BlockDeviceMappings": [
                {
                    "DeviceName": "/dev/xvda",
                    "Ebs": {
                        "VolumeSize": 8,
                        "VolumeType": "gp3",
                        "Encrypted": True,
                        "DeleteOnTermination": True,
                    },
                }
            ],
            "CreditSpecification": {"CPUCredits": "standard"},
            "UserData": {"Fn::Base64": sub(userdata)},
            "Tags": [
                {"Key": "Name", "Value": sub("${AWS::StackName}-simulator")},
                {"Key": "Project", "Value": "ccproj"},
            ],
        },
        "One supervised simulator, encrypted small disk, IMDSv2",
        ["No credentials in user data", "All motors initialize normally on each run"],
        DependsOn=["InternetRoute", "SubnetRoute", "SimulatorLogs"],
    )
    ec2["Outputs"] = {
        "InstanceId": {"Value": ref("Instance")},
        "LogGroup": {"Value": ref("SimulatorLogs")},
    }
    for filename, content in (
        ("bootstrap.json", bootstrap),
        ("platform.json", t),
        ("simulator.json", ec2),
    ):
        (HERE / filename).write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
