# Later user-requested shutdown

The project must stay online until the user requests shutdown. This procedure has **not** been run against the live project. Empty resources from the first unsuccessful creation and disposable recovery stacks were cleaned during implementation; those results do not prove a full live-platform teardown.

First export any required telemetry, report results and evaluation evidence. Preserve `ccproj-deployment.json`, `deployed-evidence.json`, and the resource ownership snapshots before deleting CloudFormation stacks. Run every AWS operation through the append-only logger, from the repository root.

```powershell
.venv\Scripts\python.exe -m scripts.aws_cli --purpose 'Snapshot simulator ownership before authorized shutdown' -- cloudformation list-stack-resources --stack-name ccproj-simulator
.venv\Scripts\python.exe -m scripts.aws_cli --purpose 'Snapshot platform ownership before authorized shutdown' -- cloudformation list-stack-resources --stack-name ccproj
.venv\Scripts\python.exe -m scripts.aws_cli --purpose 'Snapshot artifact ownership before authorized shutdown' -- cloudformation list-stack-resources --stack-name ccproj-artifacts
```

After the user requests shutdown and evidence has been exported, delete stacks in this order, waiting for each deletion. The simulator stack owns instance `i-098cf45e426dd3ab7` and its automatically deleted root volume. Platform deletion also removes CloudFront, functions, queues, API, schedules, alarms and networking-related service resources it owns. CloudFront deletion can take several minutes.

```powershell
.venv\Scripts\python.exe -m scripts.aws_cli --purpose 'User-requested simulator shutdown' -- cloudformation delete-stack --stack-name ccproj-simulator
.venv\Scripts\python.exe -m scripts.aws_cli --purpose 'Wait for simulator shutdown' -- cloudformation wait stack-delete-complete --stack-name ccproj-simulator
.venv\Scripts\python.exe -m scripts.aws_cli --purpose 'User-requested platform shutdown' -- cloudformation delete-stack --stack-name ccproj
.venv\Scripts\python.exe -m scripts.aws_cli --purpose 'Wait for platform shutdown' -- cloudformation wait stack-delete-complete --stack-name ccproj
.venv\Scripts\python.exe -m scripts.aws_cli --purpose 'User-requested artifact stack shutdown' -- cloudformation delete-stack --stack-name ccproj-artifacts
.venv\Scripts\python.exe -m scripts.aws_cli --purpose 'Wait for artifact stack shutdown' -- cloudformation wait stack-delete-complete --stack-name ccproj-artifacts
```

Established stateful resources are retained by design. Verify their exact ownership against the saved snapshots before removing them:

| Resource | Deployed identifier |
| --- | --- |
| Telemetry archive | ccproj-archive-mx5crrke5wcd |
| Athena results | ccproj-results-noqdomj6xuph |
| Frontend assets | ccproj-frontend-ipu2nmzptkhj |
| Release artifacts | ccproj-artifacts-artifacts-bllhfj9fhpbr |
| Telemetry/state table | ccproj-Data-OWJUAYGLMZZB |
| Controls table | ccproj-Controls-1SBLS2VLV34K5 |
| Cognito pool | ap-southeast-2_iJjP0yB7V |
| Notification encryption key | 1919d1aa-0ed6-488a-96b3-67c213833d3b |

For each retained bucket, use logged `s3api list-object-versions` and prepare `delete-objects` manifests containing both object versions and delete markers. Delete at most 1,000 entries per request; continue until no versions or markers remain, then use logged `delete-bucket`. Removing only current objects does not empty a versioned bucket. Do not delete source data before exporting it.

After export, use logged `dynamodb delete-table` for the two retained tables, `cognito-idp delete-user-pool` for the retained pool, and `kms schedule-key-deletion --pending-window-in-days 7` for the project encryption key. AWS requires a waiting period for KMS key deletion. The separate empty key from the failed first creation (`8a3697d6-4f91-4921-a54f-4062755636c3`) was already scheduled for deletion on 14 October.

Finally verify the saved project instance is terminated, its EBS volume removed, distribution E2QMBAOSKXNVMX absent, and all owned buckets, tables, queues, functions, alarms, schedules, budgets and log groups removed or deliberately exported and retained. Check project-tagged resources for leftovers. Recheck delayed billing; an empty resource list is not an instantaneous final invoice. Do not modify unrelated teammate resources.
