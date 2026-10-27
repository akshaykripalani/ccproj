# Cooldown investigation and default fleet profiles

On 27 October 2026, the user reported finding all seven assets faulty after leaving the demonstration unattended. Bounded DynamoDB state, controls and maintenance history showed that every asset had an enabled `alternating` profile. Thermal episodes did cool and restart automatically; the next mechanical episode latched each asset until manual repair. Automatic restart is intentionally insufficient for mechanical faults. The fleet-wide alternating configuration made eventual fleet-wide stoppage inevitable.

The same snapshot exposed a separate race: after the user's repair commands were applied, inference could still read the last pre-repair telemetry and restore a stale `Repair needed` label. `backend/predictor.py` now ignores observations older than the acknowledged command and clears obsolete repair labels after fresh, healthy running telemetry. Conditional writes preserve superseding commands and newer fault episodes. Historical maintenance records remain intact.

The user approved these defaults:

| Assets | Default behavior |
| --- | --- |
| Induction motors 01, 02 and 03 | Deterioration disabled; healthy until manually faulted |
| Centrifugal pump and cooling fan | Recoverable overheating; automatic cooldown and restart |
| Air compressor and generator | Mechanical vibration; explicit manual repair required |

Enabled profiles retain 30 simulated minutes and normal 1× speed. Profiles remain configurable. The automatic controller never repairs a mechanical fault or repeatedly restarts persistent overheating. Resetting or repairing an asset preserves its configured profile.

Regression tests cover pre-repair thermal and mechanical observations, valid subsequent episodes, stale label cleanup, concurrent newer episodes and the three/two/two defaults. The deployed repeated-cooldown test temporarily uses accelerated thermal profiles on every asset, verifies two distinct automatic restarts per asset, and restores the approved profiles afterward. Its results and final deployment state are recorded in `repeated-cooldown-live-evidence.json` and `cooldown-fleet-evidence.json`.

Run the controller exercise with `.venv/Scripts/python.exe -u -m scripts.verify_cooldown`. It uses conditional requests through the audited CLI, real gateway telemetry, the processing Lambda and the inference controller; it does not fabricate sensor readings. It reconciles an automatic recovery that races a profile request, while preserving newer human commands. Initial API-based attempts were interrupted by a connection reset and disposable-login setup failure; the first cleanup also needed integer normalization for API-returned numeric speeds. Those attempts are recorded separately in `repeated-cooldown-initial-results.json` and `repeated-cooldown-auth-setup-tests.xml` and are not counted as passing tests.

The backend release passes 86 local tests and all CloudFormation schema/security checks. The frontend production build and 38 controlled browser scenarios also pass. Deployment uses the existing project account, Sydney region, simulator EC2 and compact inference Lambda. No additional compute or shutdown schedule is introduced.
