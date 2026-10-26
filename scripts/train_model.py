"""Reproducible local training and run-isolated evaluation; export portable learned trees."""

import argparse
import datetime as dt
import hashlib
import json
import random
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, precision_recall_fscore_support

from backend.equipment import CATALOG
from backend.features import FEATURES, features, score
from simulator.equipment import Equipment

ROOT = Path(__file__).resolve().parents[1]


def generate(seed, runs):
    randomizer = random.Random(seed)
    samples, labels, groups, times, failures = [], [], [], [], {}
    for run in range(runs):
        device = list(CATALOG)[run % len(CATALOG)]
        rng = random.Random(randomizer.randrange(2**31))
        speed = rng.choice([1, 1, 5, 10])
        profile = {
            "enabled": rng.random() > 0.22,
            "speed": speed,
            "faultMode": rng.choice(["overheat", "vibration"]),
            "failureAfterMinutes": rng.uniform(20, 50),
        }
        machine = Equipment(device, rng)
        trace = []
        failure = None
        for _ in range(int(60 * 65 / (10 * speed))):
            reading = machine.sample("normal", str(run), profile)
            trace.append(reading)
            if failure is None and (reading["temperatureC"] > 75 or reading["vibrationMmS"] > 4.5):
                failure = reading["simulationTime"]
        failures[run] = failure
        window = []
        for reading in trace:
            time = reading["simulationTime"]
            if failure is not None and time >= failure:
                break
            window = [row for row in window if time - row["simulationTime"] <= 120]
            window.append(reading)
            if len(window) < 2:
                continue
            samples.append(features(window, device))
            labels.append(
                profile["faultMode"]
                if failure is not None and 0 < failure - time <= 300
                else "healthy"
            )
            groups.append(run)
            times.append(time)
    return np.array(samples), np.array(labels), np.array(groups), np.array(times), failures


def export_forest(classifier):
    result = []
    for estimator in classifier.estimators_:
        tree = estimator.tree_
        values = tree.value[:, 0, :]
        values = values / values.sum(axis=1, keepdims=True)
        result.append(
            {
                "left": tree.children_left.tolist(),
                "right": tree.children_right.tolist(),
                "feature": tree.feature.tolist(),
                "threshold": tree.threshold.tolist(),
                "value": values.tolist(),
            }
        )
    return result


def metrics(y, predicted):
    precision, recall, f1, _ = precision_recall_fscore_support(
        y != "healthy", predicted != "healthy", average="binary", zero_division=0
    )
    healthy = y == "healthy"
    return {
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "falsePositiveRate": round(float(np.mean(predicted[healthy] != "healthy")), 4),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=420)
    parser.add_argument("--seed", type=int, default=20261027)
    parser.add_argument(
        "--no-select",
        action="store_true",
        help="Evaluate a candidate without replacing the selected release",
    )
    args = parser.parse_args()
    x, y, groups, times, failures = generate(args.seed, args.runs)
    # Entire episodes, including all overlapping windows, stay in one partition.
    train_end, validation_end = int(args.runs * 0.65), int(args.runs * 0.82)
    train, valid, test = (
        groups < train_end,
        (groups >= train_end) & (groups < validation_end),
        groups >= validation_end,
    )
    model = RandomForestClassifier(
        n_estimators=32,
        max_depth=8,
        min_samples_leaf=12,
        class_weight="balanced_subsample",
        random_state=args.seed,
        n_jobs=4,
    )
    model.fit(x[train], y[train])
    healthy_index = list(model.classes_).index("healthy")
    validation_risk = 1 - model.predict_proba(x[valid])[:, healthy_index]
    thresholds = np.arange(0.35, 0.86, 0.025)
    threshold = float(
        max(
            thresholds,
            key=lambda t: precision_recall_fscore_support(
                y[valid] != "healthy", validation_risk >= t, average="binary", zero_division=0
            )[2],
        )
    )
    probabilities = model.predict_proba(x[test])
    risk = 1 - probabilities[:, healthy_index]
    fault_probabilities = probabilities.copy()
    fault_probabilities[:, healthy_index] = -1
    predicted = np.where(
        risk >= threshold, model.classes_[fault_probabilities.argmax(axis=1)], "healthy"
    )
    result = metrics(y[test], predicted)
    # Causal linear-extrapolation comparator using the same measurements/window.
    temp_time = np.divide(
        75 - x[test, 0], x[test, 2], out=np.full(sum(test), np.inf), where=x[test, 2] > 0
    )
    vib_time = np.divide(
        4.5 - x[test, 1], x[test, 3], out=np.full(sum(test), np.inf), where=x[test, 3] > 0
    )
    baseline = np.where(
        np.minimum(temp_time, vib_time) <= 5,
        np.where(temp_time < vib_time, "overheat", "vibration"),
        "healthy",
    )
    test_groups, test_times = groups[test], times[test]
    lead, missed = [], 0
    for run in sorted(set(test_groups)):
        failure = failures[int(run)]
        if failure is None:
            continue
        warnings = test_times[
            (test_groups == run)
            & (predicted != "healthy")
            & (test_times < failure)
            & (test_times >= failure - 300)
        ]
        if len(warnings):
            lead.append(float((failure - min(warnings)) / 60))
        else:
            missed += 1
    artifact = {
        "format": 1,
        "horizonMinutes": 5,
        "features": FEATURES,
        "classes": model.classes_.tolist(),
        "riskThreshold": round(threshold, 4),
        "trees": export_forest(model),
    }
    # Verify exported arithmetic against sklearn across held-out samples.
    for values, expected in zip(x[test][:500], risk[:500], strict=True):
        actual, _ = score(artifact, values.tolist())
        assert abs(actual - expected) < 1e-10
    content = json.dumps(artifact, separators=(",", ":"), allow_nan=False).encode()
    version = "rf-" + hashlib.sha256(content).hexdigest()[:12]
    artifact["version"] = version
    artifact["trainedAt"] = dt.datetime.now(dt.timezone.utc).isoformat()
    summary = {
        "version": version,
        "seed": args.seed,
        "episodes": args.runs,
        "samples": len(y),
        "split": {
            "trainingEpisodes": train_end,
            "validationEpisodes": validation_end - train_end,
            "testEpisodes": args.runs - validation_end,
        },
        "horizonMinutes": 5,
        "riskThreshold": round(threshold, 4),
        "heldOut": result,
        "trendBaseline": metrics(y[test], baseline),
        "faultClassification": classification_report(
            y[test], predicted, output_dict=True, zero_division=0
        ),
        "confusionMatrix": confusion_matrix(y[test], predicted, labels=model.classes_).tolist(),
        "classOrder": model.classes_.tolist(),
        "warningLeadMinutes": {
            "median": round(float(np.median(lead)), 2) if lead else None,
            "minimum": round(min(lead), 2) if lead else None,
            "detectedEpisodes": len(lead),
            "missedEpisodes": missed,
        },
        "exportParitySamples": min(500, sum(test)),
        "limitations": "Synthetic simulator data; results do not establish real equipment performance. Independent episodes are held out; the test set is not used for model or threshold selection. Risk scores are uncalibrated classifier scores, not guaranteed probabilities.",
    }
    summary["releaseGatePassed"] = (
        result["precision"] >= 0.75 and result["recall"] >= 0.75 and bool(lead)
    )
    destination = ROOT / "models" / version
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "model.json").write_text(
        json.dumps(artifact, separators=(",", ":")), encoding="utf-8"
    )
    (destination / "evaluation.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    if summary["releaseGatePassed"] and not args.no_select:
        (ROOT / "models" / "release.json").write_text(
            json.dumps(
                {
                    "version": version,
                    "modelPath": f"models/{version}/model.json",
                    "evaluationPath": f"models/{version}/evaluation.json",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, indent=2))
    if not summary["releaseGatePassed"]:
        raise SystemExit("Release gate failed; model must not be deployed")


if __name__ == "__main__":
    main()
