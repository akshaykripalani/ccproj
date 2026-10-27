# Current outlook and maintenance history

The deployed overview originally placed a maintenance-event list beneath the label `5-minute outlook`. Old `Fault predicted · overheating` events could therefore look like current forecasts, including events created during the all-device thermal validation. The list was historical, not a per-device current outlook.

The live CloudFront page was inspected through normal hosted login with a disposable viewer account. At inspection, the three motors, pump and fan were healthy; the compressor and generator had current mechanical faults. The old outlook panel contained earlier cooldown, restart, repair and prediction events. DynamoDB confirmed that none of the seven devices had a current overheating warning.

The panel now shows one current outlook per device, using the existing live telemetry and fresh prediction. Current faults take precedence over a nonwarning model result; offline/stopped devices and unavailable/stale predictions do not receive a healthy forecast. The prediction horizon explicitly says `Next 5 simulated minutes`. Historical events remain in a collapsed `Maintenance history` section with a description stating that they are past events. Device-detail outlook text uses the same rules.

Validation: production TypeScript/Vite build and 40 controlled browser scenarios passed. New scenarios verify that a historical overheating prediction cannot change a healthy current outlook, that an existing mechanical fault is shown even when the model warning is false, and that stale predictions are withheld. The existing mobile and accessibility checks also pass. The frontend was published to the existing private S3 bucket and CloudFront cache invalidated. Backend behavior, fault profiles and model artifacts are unchanged.

`outlook-browser-tests.json` records the controlled checks. `outlook-live-evidence.json` records the subsequent signed-in CloudFront verification. The inspection account is removed after verification.
