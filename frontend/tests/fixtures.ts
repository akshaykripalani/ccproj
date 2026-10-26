import type { Page, Route } from "@playwright/test";
import type {
  Account,
  AlertResponse,
  Config,
  Device,
  DeviceResponse,
  Reading,
  ReportParameters,
  Role,
} from "../src/types";

export const config: Config = {
  apiUrl: "https://api.example.test",
  loginDomain: "https://login.example.test",
  region: "ap-southeast-2",
  clientId: "test-client",
  userPoolId: "test-pool",
  callbackUrl: "http://localhost:5173/callback",
  logoutUrl: "http://localhost:5173/",
};
export const issuer = `https://cognito-idp.${config.region}.amazonaws.com/${config.userPoolId}`;
export const userEmail = "operator@example.test";
export function token(roles: Role[]) {
  return [
    btoa(JSON.stringify({ alg: "RS256" })),
    btoa(
      JSON.stringify({
        "cognito:groups": roles,
        sub: "test-sub",
        exp: Math.floor(Date.now() / 1000) + 600,
      }),
    ),
    "test-signature",
  ].join(".");
}
export function makeReading(id: string, index = 0): Reading {
  return {
    deviceId: id,
    eventId: `${id}:${index}`,
    observedAt: new Date(Date.now() - index * 10000).toISOString(),
    temperatureC: 55 + (index % 12) * 0.2,
    vibrationMmS: 1.5,
    powerWatts: 425,
    operatingState: "running",
  };
}
export function makeDevices(): DeviceResponse {
  return {
    serverTime: new Date().toISOString(),
    devices: ["motor-01", "motor-02", "motor-03"].map((id): Device => ({
      deviceId: id,
      name: `Factory ${id}`,
      online: true,
      lastSeen: new Date().toISOString(),
      latest: {
        ...makeReading(id),
        rules: {
          temperature: { active: false, above: 0, healthy: 3 },
          vibration: { active: false, above: 0, healthy: 3 },
        },
      },
      thresholds: {
        temperature: { field: "temperatureC", value: 75 },
        vibration: { field: "vibrationMmS", value: 4.5 },
      },
      control: {
        requestId: `initial-${id}`,
        requestedMode: "normal",
        appliedMode: "normal",
        status: "applied",
        requestedAt: new Date(Date.now() - 60000).toISOString(),
        appliedAt: new Date(Date.now() - 50000).toISOString(),
      },
    })),
  };
}

export interface MockApp {
  devices: DeviceResponse;
  alerts: AlertResponse;
  users: Account[];
  requests: {
    method: string;
    path: string;
    params: URLSearchParams;
    body: Record<string, unknown> | undefined;
  }[];
  failDevices: boolean;
  reports: "success" | "empty" | "failed";
  readingPages: boolean;
}

export async function mockApp(
  page: Page,
  roles: Role[] = ["viewer", "operator"],
  signedIn = true,
) {
  if (signedIn)
    await page.addInitScript(
      ({ issuer, config, credential, userEmail }) => {
        sessionStorage.setItem(
          `oidc.user:${issuer}:${config.clientId}`,
          JSON.stringify({
            id_token: credential,
            access_token: credential,
            refresh_token: "mock-refresh",
            token_type: "Bearer",
            scope: "openid email profile",
            expires_at: Math.floor(Date.now() / 1000) + 600,
            profile: {
              sub: "test-sub",
              email: userEmail,
              "cognito:username": userEmail,
            },
          }),
        );
      },
      { issuer, config, credential: token(roles), userEmail },
    );
  await page.route("**/config.json", (route) =>
    route.fulfill({ json: config }),
  );
  const state: MockApp = {
    devices: makeDevices(),
    alerts: { alerts: [], subscriptions: { confirmed: 1, pending: 0 } },
    users: [
      {
        username: userEmail,
        enabled: true,
        status: "CONFIRMED",
        attributes: [{ Name: "email", Value: userEmail }],
        roles,
      },
      {
        username: "viewer@example.test",
        enabled: true,
        status: "CONFIRMED",
        attributes: [{ Name: "email", Value: "viewer@example.test" }],
        roles: ["viewer"],
      },
    ],
    requests: [],
    failDevices: false,
    reports: "success",
    readingPages: false,
  };
  let parameters: ReportParameters;
  await page.route("https://api.example.test/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const body = request.postDataJSON() as Record<string, unknown> | undefined;
    state.requests.push({
      method: request.method(),
      path: url.pathname,
      params: url.searchParams,
      body,
    });
    if (!request.headers().authorization?.startsWith("Bearer ")) {
      await route.fulfill({ status: 401, json: { error: "Missing token" } });
      return;
    }
    if (url.pathname === "/devices") {
      await route.fulfill(
        state.failDevices
          ? { status: 503, json: { error: "Service temporarily unavailable" } }
          : { json: state.devices },
      );
    } else if (url.pathname.endsWith("/readings")) {
      const device = url.pathname.split("/")[2];
      await route.fulfill({
        json: {
          readings: Array.from({ length: 20 }, (_, index) =>
            makeReading(
              device,
              index + (url.searchParams.has("cursor") ? 20 : 0),
            ),
          ),
          nextCursor:
            state.readingPages && !url.searchParams.has("cursor")
              ? "page2"
              : null,
        },
      });
    } else if (url.pathname === "/alerts") {
      const device = url.searchParams.get("deviceId");
      const status = url.searchParams.get("state");
      await route.fulfill({
        json: {
          ...state.alerts,
          alerts: state.alerts.alerts.filter(
            (alert) =>
              (!device || alert.pk === device) &&
              (!status || alert.state === status),
          ),
        },
      });
    } else if (url.pathname.startsWith("/controls/")) {
      const targets = url.pathname.endsWith("/reset-all")
        ? state.devices.devices
        : state.devices.devices.filter(
            (device) => device.deviceId === url.pathname.split("/")[2],
          );
      for (const device of targets)
        device.control = {
          ...device.control,
          requestId: crypto.randomUUID(),
          requestedMode: (body?.mode ??
            "normal") as Device["control"]["requestedMode"],
          requestedAt: new Date().toISOString(),
          status: "pending",
        };
      await route.fulfill({
        status: 202,
        json:
          targets.length === 1
            ? targets[0].control
            : { controls: targets.map((device) => device.control) },
      });
    } else if (url.pathname === "/maintenance") {
      await route.fulfill({ json: { events: [] } });
    } else if (url.pathname === "/model") {
      await route.fulfill({
        json: {
          version: "rf-test",
          evaluation: {
            episodes: 420,
            heldOut: { precision: 0.903, recall: 0.943, f1: 0.923 },
            warningLeadMinutes: { median: 5 },
          },
        },
      });
    } else if (url.pathname.startsWith("/profiles/")) {
      const device = state.devices.devices.find(
        (d) => d.deviceId === url.pathname.split("/")[2],
      );
      if (device) device.profile = body as unknown as Device["profile"];
      await route.fulfill({ status: 202, json: device?.control ?? {} });
    } else if (url.pathname === "/reports") {
      parameters = body as unknown as ReportParameters;
      await route.fulfill({
        status: 202,
        json: {
          reportId: "11111111-1111-1111-1111-111111111111",
          status: "QUEUED",
        },
      });
    } else if (url.pathname.startsWith("/reports/")) {
      const row =
        parameters.report === "temperature"
          ? {
              average_temperature_c: "55.1",
              maximum_temperature_c: "58.9",
              reading_count: "100",
            }
          : parameters.report === "vibration"
            ? { breached_readings: "7" }
            : {
                average_running_power_watts: "425",
                running_reading_count: "90",
              };
      await route.fulfill({
        json: {
          reportId: url.pathname.split("/")[2],
          status: state.reports === "failed" ? "FAILED" : "SUCCEEDED",
          parameters,
          bytesScanned: 1234,
          rows:
            state.reports === "empty"
              ? []
              : [{ deviceid: "motor-01", day: parameters.start, ...row }],
          ...(state.reports === "failed"
            ? { error: "Historical query did not complete" }
            : {}),
        },
      });
    } else if (url.pathname === "/users") {
      if (request.method() === "POST")
        state.users.push({
          username: String(body?.email),
          enabled: true,
          status: "FORCE_CHANGE_PASSWORD",
          roles: body?.roles as Role[],
          attributes: [{ Name: "email", Value: String(body?.email) }],
        });
      if (request.method() === "PUT")
        state.users = state.users.map((account) =>
          account.username === body?.email
            ? { ...account, roles: body.roles as Role[] }
            : account,
        );
      await route.fulfill({ json: { users: state.users } });
    } else
      await route.fulfill({ status: 404, json: { error: "Route not found" } });
  });
  return state;
}
