import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { mockApp, config, makeReading } from "./fixtures";

test("sign-in page is concise, responsive and explains initial password setup", async ({
  page,
}) => {
  await mockApp(page, ["viewer"], false);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Equipment monitoring", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Every reading.", { exact: false })).toHaveCount(
    0,
  );
  await page.getByText("First sign-in or password trouble?").click();
  await expect(
    page.getByText("For a new account, use the temporary password", {
      exact: false,
    }),
  ).toBeVisible();
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(accessibility.violations).toEqual([]);
  await page.getByText("First sign-in or password trouble?").click();
  await page.screenshot({
    path: "../docs/ui-login-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../docs/ui-login-mobile.png",
    fullPage: true,
  });
});

test("overview shows three healthy motors and current units", async ({
  page,
}) => {
  await mockApp(page);
  await page.goto("/");
  await expect(
    page.getByRole("region", { name: "Plant overview" }),
  ).toBeVisible();
  await expect(page.getByText("Running", { exact: true })).toHaveCount(3);
  for (const id of ["motor-01", "motor-02", "motor-03"]) {
    const card = page.getByTestId(id);
    await expect(card.getByText("55.0")).toBeVisible();
    await expect(card.getByText("1.50")).toBeVisible();
    await expect(card.getByText("425")).toBeVisible();
  }
  await expect(
    page.getByRole("img", { name: /Temperature chart with 60 readings/ }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/overview-desktop.png",
    fullPage: true,
  });
});

test("controls show requested and applied states separately", async ({
  page,
}) => {
  const state = await mockApp(page);
  await page.goto("/");
  const card = page.getByTestId("motor-01");
  await page.locator(".demo-controls > summary").click();
  await page.getByRole("button", { name: "Overheat", exact: true }).click();
  await expect(card.getByText("Applying change…")).toBeVisible();
  await expect(
    page.locator(".demo-controls .control-status").getByText("Applied:"),
  ).toContainText("Normal");
  expect(
    state.requests.find((request) => request.path === "/controls/motor-01")
      ?.body,
  ).toEqual({ mode: "overheat" });
  state.devices.devices[0].control = {
    ...state.devices.devices[0].control,
    appliedMode: "overheat",
    status: "applied",
    appliedAt: new Date().toISOString(),
  };
  await expect(
    page.locator(".demo-controls .control-status").getByText("Applied:"),
  ).toContainText("Overheat");
  await expect(
    page.locator(".demo-controls .control-status").getByText(/^Applied \w/),
  ).toBeVisible();
  await expect(
    page.getByTestId("motor-02").getByText("Running", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Reset all motors" }).click();
  await page
    .getByRole("button", { name: "Confirm reset", exact: true })
    .click();
  await expect(page.getByText("Reset requested for all motors.")).toBeVisible();
});

test("viewers cannot see controls or request user management", async ({
  page,
}) => {
  const state = await mockApp(page, ["viewer"]);
  await page.goto("/");
  await expect(page.getByTestId("motor-01")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Overheat", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Team" })).toHaveCount(0);
  await page.goto("/#/users");
  await expect(
    page.getByRole("heading", { name: "Operator access required" }),
  ).toBeVisible();
  expect(state.requests.some((request) => request.path === "/users")).toBe(
    false,
  );
});

test("reset-all polls pending controls quickly and returns to normal cadence after acknowledgement", async ({
  page,
}) => {
  await page.clock.install();
  await page.clock.pauseAt(new Date(Date.now() + 1000));
  const state = await mockApp(page);
  const reads = () =>
    state.requests.filter((request) => request.path === "/devices").length;
  await page.goto("/");
  await expect(page.getByTestId("motor-03")).toBeVisible();
  await page.getByRole("button", { name: "Reset all motors" }).click();
  await page
    .getByRole("button", { name: "Confirm reset", exact: true })
    .click();
  await expect(
    page.getByRole("table").getByText("Applying change…"),
  ).toHaveCount(3);
  const pendingReads = reads();
  await page.clock.fastForward(1000);
  await expect.poll(reads).toBe(pendingReads + 1);
  // Wait for the response to finish before advancing the paused clock again.
  await expect(
    page.getByRole("button", { name: "Refresh telemetry" }).locator("svg"),
  ).not.toHaveClass(/spin/);

  for (const device of state.devices.devices)
    device.control = {
      ...device.control,
      status: "applied",
      appliedMode: "normal",
      appliedAt: new Date().toISOString(),
    };
  await page.clock.fastForward(1000);
  await expect(
    page.getByRole("table").getByText("Applying change…"),
  ).toHaveCount(0);
  const appliedReads = reads();
  await page.clock.fastForward(5000);
  expect(reads()).toBe(appliedReads);
  await page.clock.fastForward(5000);
  await expect.poll(reads).toBe(appliedReads + 1);
});

test("failed refreshes cannot keep a stale command on fast polling indefinitely", async ({
  page,
}) => {
  await page.clock.install();
  await page.clock.pauseAt(new Date(Date.now() + 1000));
  const state = await mockApp(page);
  const reads = () =>
    state.requests.filter((request) => request.path === "/devices").length;
  await page.goto("/");
  const card = page.getByTestId("motor-01");
  await page.locator(".demo-controls > summary").click();
  await page.getByRole("button", { name: "Overheat", exact: true }).click();
  await expect(card.getByText("Applying change…")).toBeVisible();
  // Finish the immediate post-command refresh before introducing the outage.
  await expect.poll(reads).toBe(2);
  state.failDevices = true;
  await page.clock.fastForward(1000);
  await expect(page.getByRole("alert")).toContainText(
    "last available readings",
  );
  const previousReads = reads();
  await page.clock.fastForward(65000);
  await expect.poll(reads).toBeGreaterThan(previousReads);
  const expiredReads = reads();
  await page.clock.fastForward(1000);
  expect(reads()).toBe(expiredReads);
  await page.clock.fastForward(9000);
  await expect.poll(reads).toBe(expiredReads + 1);
});

test("offline differs from a stopped reporting motor and timeout is visible", async ({
  page,
}) => {
  const state = await mockApp(page);
  state.devices.devices[0].online = false;
  state.devices.devices[0].lastSeen = new Date(
    Date.now() - 90000,
  ).toISOString();
  state.devices.devices[1].latest!.operatingState = "stopped";
  state.devices.devices[1].latest!.powerWatts = 0;
  state.devices.devices[2].control.status = "failed";
  state.devices.devices[2].control.reason =
    "Simulator acknowledgement timed out";
  await page.goto("/");
  await expect(
    page.getByTestId("motor-01").getByText("Offline", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByTestId("motor-02").getByText("Stopped", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByTestId("motor-03").getByText("Change not confirmed. Try again."),
  ).toBeVisible();
});

test("device detail loads all charts and pagination for 24h", async ({
  page,
}) => {
  const state = await mockApp(page);
  state.readingPages = true;
  await page.goto("/#/devices/motor-02");
  await expect(
    page.getByText("Equipment details", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Chart time range").selectOption("24");
  await expect(
    page.getByRole("img", { name: /Temperature chart with 40 readings/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: /Vibration chart with 40 readings/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: /Power draw chart with 40 readings/ }),
  ).toBeVisible();
  expect(
    state.requests.some((request) => request.params.get("cursor") === "page2"),
  ).toBe(true);
});

test("alerts filter by device and state with truthful email statuses", async ({
  page,
}) => {
  const state = await mockApp(page);
  state.alerts.subscriptions.pending = 1;
  state.alerts.alerts = [
    {
      alertId: "active",
      pk: "motor-01",
      rule: "temperature",
      state: "active",
      activatedAt: new Date().toISOString(),
      reading: { ...makeReading("motor-01"), temperatureC: 80 },
      emailStatus: "pending_confirmation",
    },
    {
      alertId: "resolved",
      pk: "motor-02",
      rule: "vibration",
      state: "resolved",
      activatedAt: new Date().toISOString(),
      resolvedAt: new Date().toISOString(),
      reading: { ...makeReading("motor-02"), vibrationMmS: 5 },
      emailStatus: "sns_accepted",
    },
  ];
  await page.goto("/#/alerts");
  await expect(
    page.getByText("Confirmation pending", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Email accepted", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Email accepted", { exact: true }),
  ).toHaveAttribute(
    "title",
    "Accepted for sending; inbox delivery is not confirmed.",
  );
  await page
    .getByRole("combobox", { name: "Equipment", exact: true })
    .selectOption("motor-02");
  await page
    .getByRole("combobox", { name: "State", exact: true })
    .selectOption("resolved");
  await expect(page.getByText("1 episodes")).toBeVisible();
  await expect(
    page.getByText("Confirmation pending", { exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("combobox", { name: "Time window", exact: true })
    .selectOption("30");
  await expect(page.getByText("Email accepted", { exact: true })).toBeVisible();
});

for (const kind of ["temperature", "vibration", "power"] as const)
  test(`${kind} report shows asynchronous result chart and CSV`, async ({
    page,
  }) => {
    const state = await mockApp(page);
    await page.goto("/#/reports");
    await page.locator(`input[value="${kind}"]`).check();
    await page.getByRole("button", { name: "Generate report" }).click();
    await expect(page.getByText("Your report is queued…")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Report results" }),
    ).toBeVisible();
    const request = state.requests.find(
      (request) => request.path === "/reports",
    );
    expect(request?.body?.report).toBe(kind);
    await expect(page.getByRole("img", { name: /report chart/ })).toBeVisible();
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export CSV" }).click();
    expect((await download).suggestedFilename()).toContain(`forge-${kind}`);
  });

test("reports show empty results and query failures without false success", async ({
  page,
}) => {
  const state = await mockApp(page);
  state.reports = "empty";
  await page.goto("/#/reports");
  await page.getByRole("button", { name: "Generate report" }).click();
  await expect(page.getByText("No readings in this range")).toBeVisible();
  state.reports = "failed";
  await page.getByRole("button", { name: "Generate report" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Historical query did not complete",
  );
});

test("report date window is validated before query starts", async ({
  page,
}) => {
  const state = await mockApp(page);
  await page.goto("/#/reports");
  await page
    .getByLabel("Start date (UTC)")
    .fill(new Date(Date.now() - 10 * 86400000).toISOString().slice(0, 10));
  await page.getByRole("button", { name: "Generate report" }).click();
  await expect(page.getByRole("alert")).toContainText("Choose up to 7 days");
  expect(state.requests.some((request) => request.path === "/reports")).toBe(
    false,
  );
});

test("operators invite accounts and update roles while protecting self", async ({
  page,
}) => {
  const state = await mockApp(page);
  await page.goto("/#/users");
  const self = page
    .getByRole("row")
    .filter({ hasText: "operator@example.test" });
  await expect(
    self.getByRole("checkbox", { name: "operator", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("Email address").fill("new@example.test");
  await page.getByRole("button", { name: "Send invitation" }).click();
  await expect(
    page.getByText("Invitation sent to new@example.test.", { exact: false }),
  ).toBeVisible();
  const invited = page.getByRole("row").filter({ hasText: "new@example.test" });
  await invited
    .getByRole("checkbox", { name: "operator", exact: true })
    .check();
  await invited.getByRole("button", { name: "Save roles" }).click();
  expect(
    state.requests.filter((request) => request.method === "PUT").at(-1)?.body,
  ).toEqual({ email: "new@example.test", roles: ["viewer", "operator"] });
});

test("API failures preserve visible readings and support retry", async ({
  page,
}) => {
  const state = await mockApp(page);
  await page.goto("/");
  await expect(page.getByTestId("motor-01")).toBeVisible();
  state.failDevices = true;
  await page.getByRole("button", { name: "Refresh telemetry" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Showing the last available readings",
  );
  await expect(page.getByTestId("motor-01")).toBeVisible();
  state.failDevices = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("hosted sign-in uses authorization code with PKCE and random state", async ({
  page,
}) => {
  await mockApp(page, ["viewer"], false);
  let authorization = "";
  await page.route(`${config.loginDomain}/**`, (route) => {
    authorization = route.request().url();
    return route.fulfill({
      contentType: "text/html",
      body: "<h1>Hosted sign-in</h1>",
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(
    page.getByRole("heading", { name: "Hosted sign-in" }),
  ).toBeVisible();
  const parameters = new URL(authorization).searchParams;
  expect(parameters.get("response_type")).toBe("code");
  expect(parameters.get("code_challenge_method")).toBe("S256");
  expect(parameters.get("code_challenge")?.length).toBe(43);
  expect(parameters.get("state")?.length).toBeGreaterThan(20);
});

test("callback rejects a missing OAuth state and clears code from URL", async ({
  page,
}) => {
  await mockApp(page, ["viewer"], false);
  await page.goto("/callback?code=untrusted&state=unknown");
  await expect(page.getByRole("alert")).toContainText(
    "Sign-in could not be completed",
  );
  expect(page.url()).not.toContain("code=");
});

test("session rejection and refresh failure return to sign-in", async ({
  page,
}) => {
  await mockApp(page);
  await page.route("https://api.example.test/**", (route) =>
    route.fulfill({ status: 401, json: { error: "Expired token" } }),
  );
  await page.route(`${config.loginDomain}/oauth2/token`, (route) =>
    route.fulfill({ status: 400, json: { error: "invalid_grant" } }),
  );
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("session has expired");
});

test("mobile navigation and dashboard have no horizontal overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApp(page);
  await page.goto("/");
  await expect(page.getByTestId("motor-03")).toBeVisible();
  await page.getByRole("link", { name: "Reports" }).click();
  await expect(
    page.getByRole("heading", { name: "Reports", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/reports-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
});

test("dashboard and report form have accessible controls and landmarks", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockApp(page);
  await page.goto("/");
  await expect(page.getByTestId("motor-01")).toBeVisible();
  const overview = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(
    overview.violations.map((item) => ({
      id: item.id,
      targets: item.nodes.map((node) => node.target),
    })),
  ).toEqual([]);
  await page.goto("/#/reports");
  await expect(
    page.getByRole("heading", { name: "Reports", exact: true }),
  ).toBeVisible();
  const report = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(
    report.violations.map((item) => ({
      id: item.id,
      targets: item.nodes.map((node) => node.target),
    })),
  ).toEqual([]);
});

test("clock advancement makes old live responses visibly stale and motors offline", async ({
  page,
}) => {
  await page.clock.install();
  const state = await mockApp(page);
  await page.goto("/");
  await expect(
    page.getByTestId("motor-01").getByText("Running", { exact: true }),
  ).toBeVisible();
  state.failDevices = true;
  await page.clock.fastForward(65000);
  await expect(
    page.getByTestId("motor-01").getByText("Offline", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toContainText(
    "last available readings",
  );
});

test("refresh token renewal replaces the access token after a read rejection", async ({
  page,
}) => {
  await mockApp(page);
  let reads = 0;
  await page.route("https://api.example.test/devices", async (route) => {
    reads += 1;
    if (reads === 1)
      await route.fulfill({ status: 401, json: { error: "Expired" } });
    else await route.fallback();
  });
  await page.route(`${config.loginDomain}/oauth2/token`, (route) =>
    route.fulfill({
      json: {
        access_token: "renewed-token",
        token_type: "Bearer",
        expires_in: 600,
        scope: "openid email profile",
      },
    }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("region", { name: "Plant overview" }),
  ).toBeVisible();
  await expect(page.getByTestId("motor-01")).toBeVisible();
  expect(reads).toBeGreaterThanOrEqual(2);
});

test("sign-out clears local tokens and requests the hosted logout URL", async ({
  page,
}) => {
  await mockApp(page);
  await page.route(`${config.loginDomain}/oauth2/revoke`, (route) =>
    route.fulfill({ body: "" }),
  );
  await page.route(`${config.loginDomain}/logout**`, (route) =>
    route.fulfill({ contentType: "text/html", body: "<h1>Signed out</h1>" }),
  );
  await page.goto("/");
  await expect(page.getByTestId("motor-01")).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Signed out" })).toBeVisible();
  expect(new URL(page.url()).searchParams.get("logout_uri")).toBe(
    config.logoutUrl,
  );
});

test("compact overview keeps a fixed heading while readings and fault indicators update", async ({
  page,
}) => {
  const state = await mockApp(page);
  const motor = state.devices.devices[1];
  motor.latest!.temperatureC = 81;
  motor.latest!.rules!.temperature.active = true;
  motor.control.appliedMode = "overheat";
  motor.control.requestedMode = "overheat";
  state.alerts.alerts = [
    {
      alertId: "fault-reference",
      pk: motor.deviceId,
      rule: "temperature",
      state: "active",
      activatedAt: new Date(Date.now() - 30000).toISOString(),
      reading: { ...makeReading(motor.deviceId), temperatureC: 81 },
      emailStatus: "sns_accepted",
    },
  ];
  await page.route("https://api.example.test/devices/*/readings*", (route) => {
    const id = new URL(route.request().url()).pathname.split("/")[2];
    const readings = Array.from({ length: 360 }, (_, index) => ({
      ...makeReading(id, index),
      observedAt: new Date(Date.now() - (359 - index) * 10000).toISOString(),
      temperatureC:
        id === "motor-02"
          ? 56 + 25 * Math.max(0, (index - 260) / 99)
          : id === "motor-01"
            ? 55
            : 57,
    }));
    return route.fulfill({ json: { readings, nextCursor: null } });
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "Overview",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator(".plant-summary")).toContainText("1 active fault");
  const chart = page.getByRole("img", {
    name: /Temperature chart with \d+ readings across all motors/,
  });
  await expect(chart).toBeVisible();
  await expect(chart.locator('.fleet-line[d*="L"]')).toHaveCount(3);
  for (const id of ["Motor 01", "Motor 02", "Motor 03"])
    await expect(chart.locator("text").filter({ hasText: id })).toHaveCount(1);
  await expect(page.getByTestId("motor-02")).toHaveClass("fault-row");
  await expect(page.getByTestId("motor-01")).not.toHaveClass("fault-row");
  await expect(
    page.getByRole("button", { name: "Overheat", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/redesign-overview-fault-desktop.png",
    fullPage: true,
    animations: "disabled",
  });
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(accessibility.violations).toEqual([]);
  await page
    .getByTestId("motor-02")
    .getByRole("button", { name: "Reset", exact: true })
    .click();
  expect(
    state.requests.find((request) => request.path === "/controls/motor-02")
      ?.body,
  ).toEqual({ mode: "normal" });
  motor.latest!.temperatureC = 55;
  motor.latest!.rules!.temperature.active = false;
  motor.control = {
    ...motor.control,
    status: "applied",
    appliedMode: "normal",
  };
  await page.getByRole("button", { name: "Refresh telemetry" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Overview",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByTestId("motor-02").getByText("Running", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".plant-summary")).toContainText("0 active faults");
  await expect(page.locator(".fault-banner")).toHaveCount(0);
});

test("reference styling and self-hosted fonts remain usable across desktop and mobile views", async ({
  page,
}) => {
  await mockApp(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const [label, width, height] of [
    ["desktop", 1440, 1000],
    ["mobile", 390, 844],
  ] as const) {
    await page.setViewportSize({ width, height });
    for (const route of [
      "overview",
      "devices/motor-01",
      "alerts",
      "reports",
      "users",
    ]) {
      await page.goto(`/#/${route}`);
      await expect(page.locator("h1")).toBeVisible();
      if (route.startsWith("devices"))
        await expect(
          page.getByRole("img", { name: /Temperature chart with 20 readings/ }),
        ).toBeVisible();
      if (route === "overview")
        await expect(page.getByTestId("motor-03")).toBeVisible();
      if (route === "users")
        await expect(
          page.getByText("operator@example.test", { exact: true }).last(),
        ).toBeVisible();
      await page.evaluate(async () => {
        // Some screens use no numeric mono text until a result arrives.
        await Promise.all([
          document.fonts.load('15px "IBM Plex Sans"'),
          document.fonts.load('13px "IBM Plex Mono"'),
        ]);
        await document.fonts.ready;
      });
      expect(
        await page.evaluate(
          () =>
            document.fonts.check('15px "IBM Plex Sans"') &&
            document.fonts.check('13px "IBM Plex Mono"'),
        ),
      ).toBe(true);
      await page.screenshot({
        path: `test-results/redesign-${route.replace("/", "-")}-${label}.png`,
        fullPage: true,
        animations: "disabled",
      });
      const layout = await page.evaluate(() => ({
        fits: document.documentElement.scrollWidth <= innerWidth,
        viewport: innerWidth,
        document: document.documentElement.scrollWidth,
        outside: [...document.querySelectorAll("body *")]
          .filter(
            (element) =>
              !element.closest(".table-scroll") &&
              element.getBoundingClientRect().right > innerWidth + 1,
          )
          .slice(0, 8)
          .map((element) => ({
            name: element.tagName,
            classes: element.className,
            right: element.getBoundingClientRect().right,
          })),
      }));
      expect(layout.fits, `${route}/${label}: ${JSON.stringify(layout)}`).toBe(
        true,
      );
    }
  }
});

test("alert history, team roles and report results pass accessibility checks", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const state = await mockApp(page);
  state.devices.devices[0].latest!.rules!.temperature.active = true;
  state.alerts.alerts = [
    {
      alertId: "episode",
      pk: "motor-01",
      rule: "temperature",
      state: "active",
      activatedAt: new Date().toISOString(),
      reading: makeReading("motor-01"),
      emailStatus: "sns_accepted",
    },
  ];
  for (const route of ["alerts", "users", "reports"]) {
    await page.goto(`/#/${route}`);
    if (route === "alerts")
      await expect(
        page.getByRole("cell", { name: "Email accepted" }),
      ).toBeVisible();
    if (route === "users")
      await expect(
        page.getByText("operator@example.test", { exact: true }),
      ).toBeVisible();
    if (route === "reports") {
      await page.getByRole("button", { name: "Generate report" }).click();
      await expect(
        page.getByRole("heading", { name: "Report results" }),
      ).toBeVisible();
    }
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    expect(
      result.violations.map((item) => ({
        id: item.id,
        targets: item.nodes.map((node) => node.target),
      })),
    ).toEqual([]);
    await page.screenshot({
      path: `test-results/copy-${route}.png`,
      fullPage: true,
      animations: "disabled",
    });
  }
});
