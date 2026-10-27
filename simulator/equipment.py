"""Seven simulated industrial assets with configurable degradation and repair."""

import math

from backend.domain import timestamp, utcnow
from backend.equipment import CATALOG, default_profile, measurements


class Equipment:
    def __init__(self, device, randomizer):
        self.device, self.random = device, randomizer
        self.sequence = 0
        self.temperature = float(CATALOG[device]["temperature"])
        self.vibration, self.power = 1.5, float(CATALOG[device]["power"])
        self.simulation_time, self.cycle_time = 0.0, 0.0
        self.cycle = 0
        self.cooling_time = 0.0
        self.last_mode = "normal"
        self.completed_cooldown = False
        self.mechanical_latched = False
        self.phase = randomizer.uniform(0, 6)
        self.period_factor = randomizer.uniform(0.9, 1.1)

    def reset(self):
        self.cycle_time, self.cooling_time = 0.0, 0.0
        self.cycle += 1
        self.mechanical_latched = False
        self.completed_cooldown = False
        self.last_mode = "normal"

    def sample(self, mode, run_id, profile=None, interval=10):
        profile = {**default_profile(self.device), **(profile or {})}
        self.sequence += 1
        if mode == "disconnect":
            return None
        speed = int(profile["speed"])
        step = interval * speed
        self.simulation_time += step
        if mode == "repair":
            self.reset()
            mode = "normal"
        if mode == "cooldown" and self.last_mode != "cooldown":
            self.cooling_time = 0
        self.last_mode = mode
        self.cycle_time += step if mode == "normal" else 0
        fault = profile["faultMode"]
        if fault == "alternating":
            fault = "overheat" if self.cycle % 2 == 0 else "vibration"
        progress = (
            self.cycle_time / (float(profile["failureAfterMinutes"]) * 60 * self.period_factor)
            if profile["enabled"]
            else 0
        )
        load = 0.7 + 0.12 * math.sin(self.simulation_time / 230 + self.phase)
        values = measurements(
            self.device,
            min(progress, 1.2),
            fault,
            load,
            self.simulation_time / 190 + self.phase,
            self.random,
        )
        if mode == "overheat":
            values["temperatureC"] = 95
        if mode == "vibration" or self.mechanical_latched:
            values["vibrationMmS"] = 7
        stopped = mode in ("cooldown", "stopped") or self.mechanical_latched
        if mode == "cooldown":
            self.cooling_time += step
            values["temperatureC"] = (
                94
                if profile["faultMode"] == "persistent_overheat"
                else CATALOG[self.device]["temperature"]
            )
            values["vibrationMmS"] = 0.2
        smoothing = 0.7
        self.temperature += (values["temperatureC"] - self.temperature) * smoothing
        self.vibration += (values["vibrationMmS"] - self.vibration) * smoothing
        self.power = 0 if stopped else values["powerWatts"]
        if self.vibration > 4.5:
            self.mechanical_latched = True
            stopped = True
            self.power = 0
        if mode == "cooldown" and self.cooling_time >= max(60, 3 * step) and self.temperature < 65:
            self.reset()
            self.completed_cooldown = True
        if stopped:
            values["metrics"]["rpm"] = 0
            for metric in ("flowLitresMin", "airflowM3Min", "outputPowerWatts"):
                if metric in values["metrics"]:
                    values["metrics"][metric] = 0
        return {
            "schemaVersion": 2,
            "eventId": f"{run_id}:{self.device}:{self.sequence}",
            "deviceId": self.device,
            "equipmentType": CATALOG[self.device]["type"],
            "observedAt": timestamp(utcnow()),
            "simulationTime": self.simulation_time,
            "simulationSpeed": speed,
            "metrics": values["metrics"],
            "temperatureC": round(self.temperature, 2),
            "vibrationMmS": round(self.vibration, 3),
            "powerWatts": round(self.power, 2),
            "operatingState": "stopped" if stopped else "running",
        }
