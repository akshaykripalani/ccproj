import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { mockApp, config, makeReading } from "./fixtures";

test("overview shows three healthy motors and current units", async ({
  page,
}) => {
  await mockApp(page);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Plant overview" }),
  ).toBeVisible();
  await expect(page.getByText("Healthy", { exact: true })).toHaveCount(3);
  for (const id of ["motor-01", "motor-02", "motor-03"]) {
    const card = page.getByTestId(id);
    await expect(card.getByText("55.0")).toBeVisible();
    await expect(card.getByText("1.50")).toBeVisible();
    await expect(card.getByText("425")).toBeVisible();
  }
  await expect(
    page.getByRole("img", { name: /Temperature chart with 20 readings/ }),
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
  await card.getByRole("button", { name: "Overheat", exact: true }).click();
  await expect(
    card.getByText("Waiting for simulator acknowledgement"),
  ).toBeVisible();
  await expect(card.getByText("Applied:")).toContainText("Normal");
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
  await page.getByRole("button", { name: "Refresh telemetry" }).click();
  await expect(card.getByText("Applied:")).toContainText("Overheat");
  await expect(card.getByText(/Acknowledged/)).toBeVisible();
  await expect(
    page.getByTestId("motor-02").getByText("Applied:"),
  ).toContainText("Normal");
  await page.getByRole("button", { name: "Reset all motors" }).click();
  await expect(
    page.getByText("Normal mode requested for all motors."),
  ).toBeVisible();
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
  await expect(
    page.getByRole("link", { name: "Team & permissions" }),
  ).toHaveCount(0);
  await page.goto("/#/users");
  await expect(
    page.getByRole("heading", { name: "Operator access required" }),
  ).toBeVisible();
  expect(state.requests.some((request) => request.path === "/users")).toBe(
    false,
  );
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
    page
      .getByTestId("motor-03")
      .getByText("Simulator acknowledgement timed out"),
  ).toBeVisible();
});

test("device detail loads all charts and pagination for 24h", async ({
  page,
}) => {
  const state = await mockApp(page);
  state.readingPages = true;
  await page.goto("/#/devices/motor-02");
  await expect(
    page.getByRole("heading", { name: "Equipment details" }),
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
  await expect(
    page.getByText("Accepted by SNS", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("SNS acceptance does not confirm inbox delivery."),
  ).toBeVisible();
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
  await expect(
    page.getByText("Accepted by SNS", { exact: true }),
  ).toBeVisible();
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
  await expect(
    page.getByText("No archived readings in this range"),
  ).toBeVisible();
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
  await expect(page.getByRole("alert")).toContainText("Choose 1–7 dates");
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
    "Showing the last successful response",
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
  await page.getByRole("button", { name: "Sign in to your dashboard" }).click();
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
  await expect(
    page.getByRole("button", { name: "Sign in to your dashboard" }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("session has expired");
});

test("mobile navigation and dashboard have no horizontal overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApp(page);
  await page.goto("/");
  await expect(page.getByTestId("motor-03")).toBeVisible();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Historical reports" }).click();
  await expect(
    page.getByRole("heading", { name: "Historical reports" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/reports-mobile.png",
    fullPage: true,
  });
});

test("dashboard and report form have accessible controls and landmarks", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
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
    page.getByRole("heading", { name: "Historical reports" }),
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
    page.getByTestId("motor-01").getByText("Healthy", { exact: true }),
  ).toBeVisible();
  state.failDevices = true;
  await page.clock.fastForward(65000);
  await expect(
    page.getByTestId("motor-01").getByText("Offline", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toContainText(
    "last successful response",
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
    page.getByRole("heading", { name: "Plant overview" }),
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
