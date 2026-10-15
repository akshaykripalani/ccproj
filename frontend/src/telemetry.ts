import type { Alert, Device, Reading } from "./types";
import { modeName, motorName } from "./format";

export interface EquipmentEvent {
  id: string;
  time: string;
  title: string;
  problem?: boolean;
}

export function equipmentEvents(
  devices: Device[],
  alerts: Alert[],
): EquipmentEvent[] {
  const events: EquipmentEvent[] = alerts.flatMap((alert) => [
    {
      id: `${alert.alertId}:active`,
      time: alert.activatedAt,
      title: `${motorName(alert.pk)} ${alert.rule === "temperature" ? "over temperature" : "high vibration"}. Alert activated.`,
      problem: alert.state === "active",
    },
    ...(alert.resolvedAt
      ? [
          {
            id: `${alert.alertId}:resolved`,
            time: alert.resolvedAt,
            title: `${motorName(alert.pk)} ${alert.rule} fault resolved.`,
          },
        ]
      : []),
  ]);
  for (const device of devices) {
    const control = device.control;
    if (control.appliedAt)
      events.push({
        id: `${device.deviceId}:applied:${control.appliedAt}`,
        time: control.appliedAt,
        title: `${motorName(device.deviceId)} ${modeName(control.appliedMode).toLowerCase()} mode applied.`,
      });
    if (control.status === "pending" && control.requestedAt)
      events.push({
        id: `${device.deviceId}:request:${control.requestId}`,
        time: control.requestedAt,
        title: `${motorName(device.deviceId)} ${modeName(control.requestedMode).toLowerCase()} requested.`,
      });
  }
  return events.sort((a, b) => b.time.localeCompare(a.time));
}

export function timeLabel(time: number | string, seconds = false) {
  return new Date(time).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    ...(seconds ? { second: "2-digit" } : {}),
    hour12: false,
  });
}

export function readingPath(
  readings: Reading[],
  x: (time: number) => number,
  y: (value: number) => number,
) {
  return readings
    .map(
      (reading, index) =>
        `${!index || Date.parse(reading.observedAt) - Date.parse(readings[index - 1].observedAt) > 25000 ? "M" : "L"}${x(Date.parse(reading.observedAt)).toFixed(1)},${y(reading.temperatureC).toFixed(1)}`,
    )
    .join(" ");
}
