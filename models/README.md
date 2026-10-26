# Predictive model releases

The selected release is recorded in `release.json`. Each `rf-*` folder contains a portable JSON forest and its independent-episode evaluation. The deployed version is a CloudFormation parameter, also returned by `GET /model` and each prediction.

## Reproduce training

```powershell
.venv\Scripts\python.exe -m venv .venv-ml
.venv-ml\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -r requirements-ml.lock.txt
.venv-ml\Scripts\python.exe -m scripts.train_model --seed 20261027
```

Training uses CPU only. Entire runs remain in one partition: 273 training, 71 validation, 76 test. The validation set selects the warning threshold. Test results do not select parameters. Seed 20261028 is a separately evaluated candidate used to exercise model promotion/rollback; the original selected release remains the reported final model. `--no-select` evaluates a candidate without changing `release.json`. A failed release gate does not change the selected release.

## Inputs, labels and limits

The eight causal features are current temperature/vibration, their trends per simulated minute, normalized power, load, and recent temperature/vibration ranges. The window spans at most two simulated minutes. Episode age, profile settings, fault schedule and future readings are not model inputs. Labels use the next five simulated minutes before the first threshold crossing. Post-fault readings are excluded from warning evaluation. Fault confirmation remains a deterministic three-reading rule.

The forest has 32 trees, maximum depth eight and minimum leaf size 12. Standard-library inference reproduces the training library's float32 input conversion; export parity is checked on 500 held-out samples. Risk scores are uncalibrated classifier scores. Results apply to this simulator, not to real equipment. Independent synthetic episodes still share the same physics assumptions.

## Deploy and roll back

```powershell
# Backend/model update, preserving the running simulator:
.venv\Scripts\python.exe -m scripts.release_backend
# Select any evaluated version, including a prior version for rollback:
.venv\Scripts\python.exe -m scripts.promote_model rf-b8af65a6f20e
```

Both paths verify account `039379078306`, explicitly use `default`, publish private S3 artifacts, enforce the evaluation gate and update through CloudFormation. `provision` is forbidden. No scientific Python packages, GPU, second EC2 instance or managed ML endpoint are needed for inference.
