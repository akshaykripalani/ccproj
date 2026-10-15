import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { mockApp, makeReading } from "./fixtures";
import { utcDate } from "../src/format";

test("last-reading ages tick between polls and row sparklines use real history", async ({
  page,
}) => {
  await page.clock.install();
  await page.clock.pauseAt(new Date(Date.now() + 1000));
  const state = await mockApp(page);
  await page.goto("/");
  const row = page.getByTestId("motor-01");
  await expect(row.locator(".seen")).toContainText("0s ago");
  await expect(
    row
      .getByRole("img", { name: /temperature over the last 30 minutes/ })
      .locator("path"),
  ).toHaveAttribute("d", /L/);
  const reads = state.requests.filter((r) => r.path === "/devices").length;
  await page.clock.fastForward(2000);
  await expect(row.locator(".seen")).toContainText("2s ago");
  expect(state.requests.filter((r) => r.path === "/devices")).toHaveLength(
    reads,
  );
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true }),
  ).toBeVisible();
  expect(
    await page
      .locator("h1")
      .evaluate((e) => parseFloat(getComputedStyle(e).fontSize)),
  ).toBeLessThanOrEqual(24);
});

test("fleet chart fits available data and supports shared hover, keyboard inspection and event linking", async ({
  page,
}) => {
  await mockApp(page);
  await page.goto("/");
  const chart = page.getByRole("img", {
    name: /Temperature chart with 60 readings across all motors/,
  });
  await expect(chart).toBeVisible();
  const duration = await chart.evaluate(
    (element) =>
      Number(element.getAttribute("data-window-end")) -
      Number(element.getAttribute("data-window-start")),
  );
  expect(duration).toBeLessThan(300000);
  expect(duration).toBeGreaterThan(150000);
  const bounds = (await chart.boundingBox())!;
  await chart.hover({
    position: { x: bounds.width * 0.45, y: bounds.height * 0.5 },
  });
  await expect(chart.locator(".chart-crosshair circle")).toHaveCount(3);
  const readout = page.locator(".chart-readout.inspecting");
  for (const motor of ["Motor 01", "Motor 02", "Motor 03"])
    await expect(readout).toContainText(motor);
  await expect(readout).not.toContainText("—");
  const scrubber = page.getByRole("slider", { name: "Inspect chart time" });
  await scrubber.focus();
  await scrubber.press("Home");
  await expect(scrubber).toHaveValue("0");
  await expect(chart.locator(".chart-crosshair circle")).toHaveCount(3);
  await chart.locator(".event-marker").last().hover();
  await expect(page.locator(".event-log .event-selected")).toContainText(
    "Motor 03",
  );
  await expect(chart.locator(".event-guide")).toHaveCount(1);
});

test("reset-all requires confirmation and cancel sends no command", async ({
  page,
}) => {
  const state = await mockApp(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Reset all motors" }).click();
  const dialog = page.getByRole("dialog", { name: "Reset all three motors?" });
  await expect(dialog).toBeVisible();
  expect(
    state.requests.filter((r) => r.path.startsWith("/controls")),
  ).toHaveLength(0);
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).not.toBeVisible();
  expect(
    state.requests.filter((r) => r.path.startsWith("/controls")),
  ).toHaveLength(0);
  await page.getByRole("button", { name: "Reset all motors" }).click();
  await dialog.getByRole("button", { name: "Confirm reset" }).click();
  await expect(
    page.getByRole("table").getByText(/Normal requested → Applying change…/),
  ).toHaveCount(3);
  expect(
    state.requests.filter((r) => r.path === "/controls/reset-all"),
  ).toHaveLength(1);
});

test("mobile cards expose every metric and all navigation at 320 and 390 pixels", async ({
  page,
}) => {
  await mockApp(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/");
    await expect(page.getByTestId("motor-03")).toBeVisible();
    for (const id of ["motor-01", "motor-02", "motor-03"]) {
      const row = page.getByTestId(id);
      await expect(row.locator("td[data-label]")).toHaveCount(3);
      for (const metric of await row.locator("td[data-label]").all()) {
        const bounds = (await metric.boundingBox())!;
        expect(bounds.x).toBeGreaterThanOrEqual(0);
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
      }
      await expect(row.locator(".seen")).toContainText("Last reading");
    }
    expect(
      await page
        .locator(".motor-table .table-scroll")
        .evaluate((element) => element.scrollWidth <= element.clientWidth),
    ).toBe(true);
    await expect(page.getByRole("link", { name: /details/i })).toHaveCount(0);
    await page.getByRole("link", { name: "Team", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Team", exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.goto("/");
  await expect(page.getByTestId("motor-03")).toBeVisible();
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(accessibility.violations).toEqual([]);
  await page.screenshot({
    path: "test-results/instruments-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
});

test("equipment skeleton and value changes respect reduced motion", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const state = await mockApp(page);
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("https://api.example.test/devices", async (route) => {
    await held;
    await route.fulfill({ json: state.devices });
  });
  await page.goto("/");
  await expect(
    page.getByRole("status", { name: "Loading equipment readings" }),
  ).toBeVisible();
  expect(
    await page
      .locator(".skeleton-row span")
      .first()
      .evaluate((element) => getComputedStyle(element).animationName),
  ).toBe("none");
  release();
  await expect(page.getByTestId("motor-01")).toBeVisible();
  state.devices.devices[0].latest!.temperatureC = 81;
  await page.getByRole("button", { name: "Refresh telemetry" }).click();
  const row = page.getByTestId("motor-01");
  await expect(row.getByText("81.0", { exact: true })).toBeVisible();
  expect(
    await row
      .locator(".value-flash")
      .first()
      .evaluate((element) => getComputedStyle(element).animationName),
  ).toBe("none");
  expect(
    await row
      .locator(".gauge-track > span")
      .first()
      .evaluate((element) => getComputedStyle(element).transitionDuration),
  ).toBe("0s");
});

test("detail charts share inspection, expose metadata and use a zero power baseline", async ({
  page,
}) => {
  const state = await mockApp(page);
  state.alerts.alerts = [
    {
      alertId: "recent-detail",
      pk: "motor-01",
      rule: "vibration",
      state: "resolved",
      activatedAt: new Date(Date.now() - 120000).toISOString(),
      resolvedAt: new Date(Date.now() - 60000).toISOString(),
      reading: makeReading("motor-01"),
      emailStatus: "sns_accepted",
    },
  ];
  await page.goto("/#/devices/motor-01");
  await expect(
    page.getByRole("heading", { name: "Motor 01", exact: true }),
  ).toHaveCount(1);
  await expect(
    page.getByRole("heading", { name: "Equipment details", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Recent alerts", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".motor-alert-list")).toContainText(
    "High vibration · resolved",
  );
  await expect(page.locator(".motor-table")).toHaveCount(0);
  const temp = page.getByRole("img", {
    name: /Temperature chart with 20 readings/,
  });
  const power = page.getByRole("img", {
    name: /Power draw chart with 20 readings/,
  });
  await expect(power).toBeVisible();
  await expect(power.getByText("0", { exact: true })).toBeVisible();
  await expect(power.getByText("600", { exact: true })).toBeVisible();
  const bounds = (await temp.boundingBox())!;
  await temp.hover({ position: { x: bounds.width / 2, y: bounds.height / 2 } });
  await expect
    .poll(() =>
      page
        .locator(".recharts-tooltip-wrapper")
        .evaluateAll(
          (elements) =>
            elements.filter(
              (element) => getComputedStyle(element).visibility === "visible",
            ).length,
        ),
    )
    .toBe(3);
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(accessibility.violations).toEqual([]);
});

test("alert timeline includes ongoing episodes that began before its visible window", async ({
  page,
}) => {
  const state = await mockApp(page);
  state.alerts.alerts = [
    {
      alertId: "ongoing-old",
      pk: "motor-02",
      rule: "temperature",
      state: "active",
      activatedAt: new Date(Date.now() - 26 * 3600000).toISOString(),
      reading: { ...makeReading("motor-02"), temperatureC: 81 },
      emailStatus: "sns_accepted",
    },
  ];
  state.devices.devices[1].latest!.rules!.temperature = {
    active: true,
    above: 3,
    healthy: 0,
    alertId: `${state.alerts.alerts[0].activatedAt}#temperature#event`,
  };
  await page.goto("/#/alerts");
  await expect(page.locator(".episode-bar.active")).toHaveCount(1);
  await expect(page.locator(".episode-bar.active")).toHaveCSS("left", "0px");
  await page.locator(".episode-bar.active").focus();
  await expect(page.locator(".episode-caption")).toContainText(
    "Motor 02 · temperature · active",
  );
  await expect(page.locator(".alert-context")).toContainText("1 confirmed");
  await expect(page.locator(".alert-context")).toContainText("0 pending");
  await expect(page).toHaveTitle(/^\(1\) Alerts/);
  await expect(page.locator(".fault-banner")).toContainText("Active for");
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(accessibility.violations).toEqual([]);
});

test("report shortcuts retain query bounds and recent results reopen without new queries", async ({
  page,
}) => {
  const state = await mockApp(page);
  await page.goto("/#/reports");
  await page.getByRole("button", { name: "Last 7 days", exact: true }).click();
  await expect(page.getByLabel("Start date (UTC)")).toHaveValue(utcDate(-6));
  await expect(page.getByLabel("End date (UTC)")).toHaveValue(utcDate());
  expect(
    state.requests.filter((r) => r.path === "/reports" && r.method === "POST"),
  ).toHaveLength(0);
  await page.getByRole("button", { name: "Today", exact: true }).click();
  await page.getByRole("button", { name: "Generate report" }).click();
  await expect(
    page.getByRole("heading", { name: "Report results", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await page.getByRole("link", { name: "Reports", exact: true }).click();
  await page
    .locator(".recent-reports")
    .getByRole("button", { name: /Temperature ·/ })
    .click();
  await expect(
    page.getByRole("heading", { name: "Report results", exact: true }),
  ).toBeVisible();
  expect(
    state.requests.filter((r) => r.path === "/reports" && r.method === "POST"),
  ).toHaveLength(1);
  await expect(
    page.getByRole("button", { name: "Last 30 days", exact: true }),
  ).toHaveCount(0);
});
