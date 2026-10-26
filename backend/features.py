"""The identical causal feature transform is used in training and deployed inference."""

import struct

from backend.equipment import CATALOG

FEATURES = [
    "temperatureC",
    "vibrationMmS",
    "temperatureTrend",
    "vibrationTrend",
    "powerRatio",
    "loadPercent",
    "temperatureRange",
    "vibrationRange",
]


def features(window, device):
    current = window[-1]
    elapsed = max(10, float(current["simulationTime"]) - float(window[0]["simulationTime"])) / 60
    temperatures = [float(row["temperatureC"]) for row in window]
    vibrations = [float(row["vibrationMmS"]) for row in window]
    return [
        temperatures[-1],
        vibrations[-1],
        (temperatures[-1] - temperatures[0]) / elapsed,
        (vibrations[-1] - vibrations[0]) / elapsed,
        float(current["powerWatts"]) / CATALOG[device]["power"],
        float(current.get("metrics", {}).get("loadPercent", 70)),
        max(temperatures) - min(temperatures),
        max(vibrations) - min(vibrations),
    ]


def score(model, values):
    """Portable learned-tree inference; training libraries are unnecessary on Lambda."""
    # sklearn's tree predictor converts inputs to float32 before threshold comparisons.
    values = [struct.unpack("f", struct.pack("f", float(value)))[0] for value in values]
    probabilities = [0.0] * len(model["classes"])
    for tree in model["trees"]:
        node = 0
        while tree["left"][node] != -1:
            node = (
                tree["left"][node]
                if values[tree["feature"][node]] <= tree["threshold"][node]
                else tree["right"][node]
            )
        for index, value in enumerate(tree["value"][node]):
            probabilities[index] += value / len(model["trees"])
    by_class = dict(zip(model["classes"], probabilities, strict=True))
    fault = max((key for key in by_class if key != "healthy"), key=by_class.get)
    return 1 - by_class.get("healthy", 1), fault
