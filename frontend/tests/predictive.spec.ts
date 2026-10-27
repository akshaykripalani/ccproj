import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApp } from "./fixtures";

test("seven assets display warnings, measurements and a configurable profile", async ({
  page,
}) => {
  const state = await mockApp(page);
  const base = state.devices.devices[0];
  for (const id of ["pump-01", "compressor-01", "fan-01", "generator-01"])
    state.devices.devices.push({
      ...structuredClone(base),
      deviceId: id,
      latest: {
        ...base.latest!,
        deviceId: id,
        metrics: { loadPercent: 70, rpm: 1480, pressureBar: 3.2 },
      },
      profile: {
        enabled: true,
        speed: 1,
        failureAfterMinutes: 30,
        faultMode: "overheat",
      },
    });
  const pump = state.devices.devices.find((d) => d.deviceId === "pump-01")!;
  pump.prediction = {
    modelVersion: "rf-test",
    warning: true,
    faultType: "overheat",
    riskScore: 0.91,
    horizonMinutes: 5,
    at: new Date().toISOString(),
    sourceObservedAt: new Date().toISOString(),
  };
  await page.goto("/");
  await expect(
    page.getByTestId("pump-01").getByText("Warning", { exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("generator-01")).toBeVisible();
  await page
    .getByRole("link", { name: "Centrifugal pump", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Centrifugal pump", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Risk score 91/100", { exact: false }),
  ).toBeVisible();
  await expect(page.getByText("Pressure", { exact: true })).toBeVisible();
  await page.goto("/#/overview");
  await page.getByText("Fault simulation", { exact: false }).click();
  await page
    .getByRole("combobox", { name: "Equipment", exact: true })
    .selectOption("pump-01");
  await page.getByLabel("Demo speed").selectOption("10");
  await page.getByLabel("Failure mode").selectOption("vibration");
  await page.getByRole("button", { name: "Apply profile" }).click();
  expect(
    state.requests.some(
      (r) =>
        r.path === "/profiles/pump-01" &&
        r.body?.speed === 10 &&
        r.body?.faultMode === "vibration",
    ),
  ).toBe(true);
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
});

test("manual repair is explicit and viewers cannot change profiles", async ({
  page,
}) => {
  const state = await mockApp(page);
  state.devices.devices[0].latest!.rules!.vibration.active = true;
  state.devices.devices[0].control.maintenanceAction = "Repair needed";
  await page.goto("/");
  await expect(
    page.getByTestId("motor-01").getByText("Fault", { exact: true }),
  ).toBeVisible();
  await page
    .getByTestId("motor-01")
    .getByRole("button", { name: "Repair", exact: true })
    .click();
  expect(
    state.requests.some(
      (r) => r.path === "/controls/motor-01" && r.body?.mode === "repair",
    ),
  ).toBe(true);
  state.devices.devices[0].latest!.rules!.vibration.active = false;
  state.devices.devices[0].control.status = "applied";
  state.devices.devices[0].control.maintenanceAction = "Repaired";
  await expect(
    page.getByTestId("motor-01").getByText("Healthy", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByTestId("motor-01")
      .getByRole("button", { name: "Reset", exact: true }),
  ).toHaveCount(0);
});

test("mobile predictive maintenance remains within the viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApp(page, ["viewer"]);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Predictive maintenance" }),
  ).toBeVisible();
  await expect(
    page.getByText("Fault simulation", { exact: false }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("current outlook stays healthy when history contains old overheating predictions", async ({
  page,
}) => {
  const state = await mockApp(page);
  state.devices.devices[0].prediction = {
    modelVersion: "rf-test",
    warning: false,
    faultType: "overheat",
    riskScore: 0,
    horizonMinutes: 5,
    at: new Date().toISOString(),
    sourceObservedAt: new Date().toISOString(),
  };
  await page.route("https://api.example.test/maintenance", (route) =>
    route.fulfill({
      json: {
        events: [
          {
            deviceId: "motor-01",
            action: "Fault predicted",
            faultType: "overheat",
            at: new Date(Date.now() - 3600000).toISOString(),
            sk: "old-warning",
          },
        ],
      },
    }),
  );
  await page.goto("/");
  await expect(page.getByTestId("outlook-motor-01")).toContainText(
    "No approaching fault detected.",
  );
  await expect(
    page.getByText("Fault predicted", { exact: false }),
  ).not.toBeVisible();
  await page.getByText("Maintenance history", { exact: true }).click();
  await expect(
    page.getByText("Fault predicted", { exact: false }),
  ).toBeVisible();
  await expect(page.getByTestId("outlook-motor-01")).not.toContainText(
    "Overheating risk",
  );
});

test("current mechanical faults override a nonwarning model score and stale predictions expire", async ({
  page,
}) => {
  const state = await mockApp(page);
  const [mechanical, stale, warning] = state.devices.devices;
  mechanical.latest!.rules!.vibration.active = true;
  const prediction = {
    modelVersion: "rf-test",
    warning: false,
    faultType: "vibration",
    riskScore: 0.2,
    horizonMinutes: 5,
    at: new Date().toISOString(),
    sourceObservedAt: new Date().toISOString(),
  };
  mechanical.prediction = prediction;
  stale.prediction = {
    ...prediction,
    warning: true,
    at: new Date(Date.now() - 120000).toISOString(),
  };
  warning.prediction = { ...prediction, warning: true };
  await page.goto("/");
  await expect(page.getByTestId("outlook-motor-01")).toContainText(
    "Current fault · mechanical",
  );
  await expect(page.getByTestId("outlook-motor-02")).toContainText(
    "Prediction updating as readings arrive.",
  );
  await expect(page.getByTestId("outlook-motor-03")).toContainText(
    "Mechanical fault risk · next 5 simulated min",
  );
});
