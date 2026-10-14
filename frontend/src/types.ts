export type Mode = "normal" | "overheat" | "vibration" | "disconnect";
export type Role = "viewer" | "operator";
export interface Config {
  region: string;
  apiUrl: string;
  clientId: string;
  userPoolId: string;
  loginDomain: string;
  callbackUrl: string;
  logoutUrl: string;
}
export interface Reading {
  eventId: string;
  deviceId: string;
  observedAt: string;
  receivedAt?: string;
  temperatureC: number;
  vibrationMmS: number;
  powerWatts: number;
  operatingState: string;
}
export interface Rule {
  active: boolean;
  above: number;
  healthy: number;
  alertId?: string;
}
export interface Control {
  requestId?: string;
  requestedMode: Mode;
  appliedMode?: Mode;
  status: "pending" | "applied" | "failed";
  requestedAt?: string;
  appliedAt?: string;
  reason?: string;
}
export interface Device {
  deviceId: string;
  name: string;
  online: boolean;
  lastSeen?: string;
  latest: (Reading & { rules?: Record<string, Rule> }) | null;
  thresholds: Record<string, { field: string; value: number }>;
  control: Control;
}
export interface DeviceResponse {
  devices: Device[];
  serverTime: string;
}
export interface Alert {
  alertId: string;
  pk: string;
  rule: string;
  state: "active" | "resolved";
  activatedAt: string;
  resolvedAt?: string;
  reading: Reading;
  emailStatus: string;
}
export interface AlertResponse {
  alerts: Alert[];
  subscriptions: { confirmed: number; pending: number };
}
export type ReportKind = "temperature" | "vibration" | "power";
export interface ReportParameters {
  report: ReportKind;
  start: string;
  end: string;
  deviceId?: string;
}
export interface Report {
  reportId: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
  parameters?: ReportParameters;
  bytesScanned?: number;
  rows?: Record<string, string | null>[];
  error?: string;
}
export interface Account {
  username: string;
  enabled: boolean;
  status: string;
  roles: Role[];
  attributes: { Name: string; Value: string }[];
}
