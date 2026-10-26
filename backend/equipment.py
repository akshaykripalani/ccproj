"""Equipment catalog and repeatable synthetic physics; no AWS or ML dependencies."""

import math
from decimal import Decimal

CATALOG = {
    "motor-01": {
        "name": "Induction motor 01",
        "type": "induction_motor",
        "temperature": 52,
        "power": 420,
    },
    "motor-02": {
        "name": "Induction motor 02",
        "type": "induction_motor",
        "temperature": 50,
        "power": 480,
    },
    "motor-03": {
        "name": "Induction motor 03",
        "type": "induction_motor",
        "temperature": 54,
        "power": 560,
    },
    "pump-01": {
        "name": "Centrifugal pump",
        "type": "centrifugal_pump",
        "temperature": 46,
        "power": 750,
    },
    "compressor-01": {
        "name": "Air compressor",
        "type": "air_compressor",
        "temperature": 55,
        "power": 1100,
    },
    "fan-01": {"name": "Cooling fan", "type": "cooling_fan", "temperature": 40, "power": 180},
    "generator-01": {"name": "Generator", "type": "generator", "temperature": 57, "power": 160},
}
DEFAULT_PROFILE = {
    "enabled": True,
    "failureAfterMinutes": 30,
    "faultMode": "alternating",
    "speed": 1,
}


def validate_profile(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULT_PROFILE):
        raise ValueError("Profile fields: enabled, failureAfterMinutes, faultMode, speed")
    result = {**DEFAULT_PROFILE, **value}
    if type(result["enabled"]) is not bool:
        raise ValueError("enabled must be boolean")
    if (
        type(result["failureAfterMinutes"]) not in (int, float, Decimal)
        or not 10 <= result["failureAfterMinutes"] <= 120
    ):
        raise ValueError("failureAfterMinutes must be 10-120 simulated minutes")
    if result["faultMode"] not in ("overheat", "vibration", "alternating", "persistent_overheat"):
        raise ValueError("Unsupported faultMode")
    if type(result["speed"]) not in (int, Decimal) or result["speed"] not in (1, 5, 10):
        raise ValueError("speed must be 1, 5 or 10")
    result["speed"] = int(result["speed"])
    result["failureAfterMinutes"] = float(result["failureAfterMinutes"])
    return result


def measurements(device, progress, fault, load, phase, randomizer):
    """Latent degradation becomes observable gradually; progress is never an ML feature."""
    spec = CATALOG[device]
    damage = max(0, (progress - 0.38) / 0.62) ** 1.7
    thermal = fault in ("overheat", "persistent_overheat")
    temperature = spec["temperature"] + 5 * (load - 0.7) + 0.9 * math.sin(phase)
    vibration = 1.45 + 0.22 * load + 0.08 * math.sin(phase * 1.3)
    temperature += (78 - spec["temperature"]) * damage if thermal else 3 * damage
    vibration += 3.5 * damage if fault == "vibration" else 0.12 * damage
    power = spec["power"] * (0.75 + 0.35 * load + 0.12 * damage)
    temperature += randomizer.gauss(0, 0.25)
    vibration += randomizer.gauss(0, 0.035)
    metrics = {
        "loadPercent": round(load * 100, 1),
        "rpm": round(1480 * (1 - 0.08 * damage) + randomizer.gauss(0, 3), 1),
    }
    kind = spec["type"]
    if kind == "centrifugal_pump":
        metrics.update(
            flowLitresMin=round(max(0, 90 * (1 - 0.35 * damage)), 1),
            pressureBar=round(max(0, 3.2 * (1 - 0.2 * damage)), 2),
        )
    elif kind == "air_compressor":
        metrics.update(pressureBar=round(max(0, 8 * (1 - 0.22 * damage)), 2))
    elif kind == "cooling_fan":
        metrics.update(airflowM3Min=round(max(0, 65 * (1 - 0.4 * damage)), 1))
    elif kind == "generator":
        metrics.update(
            outputPowerWatts=round(max(0, 3000 * load * (1 - 0.15 * damage)), 1),
            voltage=round(230 - 8 * damage + randomizer.gauss(0, 0.5), 1),
            frequencyHz=round(50 - 0.4 * damage + randomizer.gauss(0, 0.03), 2),
        )
    return {
        "temperatureC": round(temperature, 2),
        "vibrationMmS": round(vibration, 3),
        "powerWatts": round(power, 2),
        "metrics": metrics,
    }
