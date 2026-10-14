export function number(value: unknown, decimals = 1) {
  return value === null ||
    value === undefined ||
    !Number.isFinite(Number(value))
    ? "—"
    : Number(value).toLocaleString(undefined, {
        maximumFractionDigits: decimals,
        minimumFractionDigits: decimals,
      });
}
export function when(value?: string) {
  return value
    ? new Date(value).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "No readings yet";
}
export function ago(value?: string, now = Date.now()) {
  if (!value) return "No readings yet";
  const seconds = Math.max(0, Math.round((now - Date.parse(value)) / 1000));
  return seconds < 60
    ? `${seconds}s ago`
    : seconds < 3600
      ? `${Math.floor(seconds / 60)}m ago`
      : `${Math.floor(seconds / 3600)}h ago`;
}
export function motorName(id: string) {
  return `Motor ${id.slice(-2)}`;
}
export function utcDate(offset = 0) {
  return new Date(Date.now() + offset * 86400000).toISOString().slice(0, 10);
}
export function modeName(mode?: string) {
  return (
    (
      {
        normal: "Normal",
        overheat: "Overheat",
        vibration: "Vibration fault",
        disconnect: "Disconnected",
      } as Record<string, string>
    )[mode ?? ""] ?? "Not acknowledged"
  );
}
