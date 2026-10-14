import { expect, test, type Page } from "@playwright/test";

async function login(page: Page, role: "OPERATOR" | "VIEWER") {
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/amazoncognito.com/);
  await page
    .locator('input[name="password"]:visible')
    .first()
    .waitFor({ state: "visible" });
  // Avoid recording secret values in locator failure call logs, traces, or source files.
  await page.evaluate(
    ({ email, password }) => {
      const username = [
        ...document.querySelectorAll<HTMLInputElement>(
          'input[name="username"]',
        ),
      ].find((input) => input.offsetParent !== null);
      const credential = [
        ...document.querySelectorAll<HTMLInputElement>(
          'input[name="password"]',
        ),
      ].find((input) => input.offsetParent !== null);
      if (!username || !credential)
        throw new Error("Hosted login fields were not found");
      username.value = email;
      credential.value = password;
      username.dispatchEvent(new Event("input", { bubbles: true }));
      credential.dispatchEvent(new Event("input", { bubbles: true }));
    },
    {
      email: process.env[`CCPROJ_${role}_EMAIL`]!,
      password: process.env[`CCPROJ_${role}_PASSWORD`]!,
    },
  );
  await page
    .locator(
      'input[name="signInSubmitButton"]:visible, button[name="signInSubmitButton"]:visible',
    )
    .first()
    .click();
  await expect(
    page.getByRole("region", { name: "Plant overview" }),
  ).toBeVisible();
  expect(page.url()).not.toContain("code=");
}

test("real hosted PKCE login, current motors, live charts and protected viewer UI", async ({
  page,
  browser,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.name));
  const csp: string[] = [];
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (event) => {
      (window as Window & { cspViolations?: string[] }).cspViolations ??= [];
      (window as Window & { cspViolations?: string[] }).cspViolations!.push(
        event.violatedDirective,
      );
    });
  });
  await login(page, "OPERATOR");
  await expect(page.getByText("Running", { exact: true })).toHaveCount(3);
  await page.getByRole("link", { name: "Equipment", exact: true }).click();
  await page.getByRole("link", { name: "Motor 01", exact: true }).click();
  await expect(
    page.getByRole("img", { name: /Temperature chart with [1-9]\d* readings/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: /Vibration chart with [1-9]\d* readings/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: /Power draw chart with [1-9]\d* readings/ }),
  ).toBeVisible();
  await page.getByLabel("Chart time range").selectOption("24");
  await expect(
    page.getByRole("img", { name: /Temperature chart with [1-9]\d* readings/ }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/ui-device-desktop.png",
    fullPage: true,
  });
  csp.push(
    ...(await page.evaluate(
      () =>
        (window as Window & { cspViolations?: string[] }).cspViolations ?? [],
    )),
  );
  expect(errors).toEqual([]);
  expect(csp).toEqual([]);
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Plant overview" }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: /Temperature chart with [1-9]\d* readings/ }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/ui-overview-desktop.png",
    fullPage: true,
    animations: "disabled",
  });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  try {
    const viewer = await context.newPage();
    await login(viewer, "VIEWER");
    await expect(
      viewer.getByRole("button", { name: "Overheat", exact: true }),
    ).toHaveCount(0);
    await viewer.goto("/#/users");
    await expect(
      viewer.getByRole("heading", { name: "Operator access required" }),
    ).toBeVisible();
    await viewer.goto("/#/overview");
    await expect(
      viewer.getByRole("img", {
        name: /Temperature chart with [1-9]\d* readings/,
      }),
    ).toBeVisible();
    await viewer.screenshot({
      path: "../docs/ui-overview-mobile.png",
      fullPage: true,
    });
    expect(
      await viewer.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await viewer.getByRole("link", { name: "Alerts" }).click();
    await expect(
      viewer.getByRole("heading", { name: "Alerts & events" }),
    ).toBeVisible();
  } finally {
    await context.close();
  }
});

test("browser fault controls receive acknowledgement, produce alerts, and reset shared motors", async ({
  page,
}) => {
  test.setTimeout(360000);
  await login(page, "OPERATOR");
  const first = page.getByTestId("motor-01");
  const second = page.getByTestId("motor-02");
  try {
    await page.locator(".demo-controls > summary").click();
    await page.getByRole("button", { name: "Overheat", exact: true }).click();
    await expect(first.getByText("Requested:")).toContainText("Overheat");
    await expect(first.getByText("Applied:")).toContainText("Overheat");
    await expect(
      first.getByText("Over temperature", { exact: true }),
    ).toBeVisible();
    await expect(page.locator(".plant-summary")).toContainText("1 active fault");
    await expect(second.getByText("Running", { exact: true })).toBeVisible();
    await page.getByLabel("Motor", { exact: true }).selectOption("motor-02");
    await page.getByRole("button", { name: "Vibration fault", exact: true }).click();
    await expect(second.getByText("Applied:")).toContainText("Vibration fault");
    await expect(
      second.getByText("High vibration", { exact: true }),
    ).toBeVisible();
    await expect(page.locator(".plant-summary")).toContainText("2 active faults");
    await page.getByRole("link", { name: "Alerts" }).click();
    await expect(
      page
        .getByRole("row")
        .filter({ hasText: "Motor 01" })
        .filter({ hasText: "active" })
        .first(),
    ).toBeVisible();
    await expect(
      page
        .getByRole("row")
        .filter({ hasText: "Motor 02" })
        .filter({ hasText: "active" })
        .first(),
    ).toBeVisible();
    await page.screenshot({
      path: "../docs/ui-alerts-desktop.png",
      fullPage: true,
    });
    await page.getByRole("link", { name: "Overview", exact: true }).click();
    await first.getByRole("button", { name: "Reset", exact: true }).click();
    await second.getByRole("button", { name: "Reset", exact: true }).click();
    await expect(first.getByText("Running", { exact: true })).toBeVisible();
    await expect(second.getByText("Running", { exact: true })).toBeVisible();
    await page.locator(".demo-controls > summary").click();
    await page.getByRole("button", { name: "Disconnect", exact: true }).click();
    await expect(first.getByText("Applied:")).toContainText("Disconnected");
    await expect(first.getByText("Offline", { exact: true })).toBeVisible();
    await expect(second.getByText("Running", { exact: true })).toBeVisible();
  } finally {
    // A separate browser request restores the shared motors even after a UI assertion fails.
    await page.evaluate(async () => {
      const config = await (await fetch("/config.json")).json();
      const issuer = `https://cognito-idp.${config.region}.amazonaws.com/${config.userPoolId}`;
      const session = JSON.parse(
        sessionStorage.getItem(`oidc.user:${issuer}:${config.clientId}`) ||
          "{}",
      );
      const result = await fetch(config.apiUrl + "/controls/reset-all", {
        method: "POST",
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (!result.ok)
        throw new Error("Final motor restoration request was rejected");
    });
  }
  await page.getByRole("button", { name: "Refresh telemetry" }).click();
  await expect(page.getByText("Running", { exact: true })).toHaveCount(3);
  await page.screenshot({
    path: "../docs/ui-overview-desktop.png",
    fullPage: true,
  });
});

test("three deployed Athena reports render results and CSV downloads", async ({
  page,
}) => {
  await login(page, "OPERATOR");
  await page.getByRole("link", { name: "Reports" }).click();
  for (const kind of ["temperature", "vibration", "power"]) {
    await page.locator(`input[value="${kind}"]`).check();
    await page.getByRole("button", { name: "Generate report" }).click();
    await expect(
      page.getByRole("heading", { name: "Report results" }),
    ).toBeVisible();
    await expect(page.getByRole("img", { name: /report chart/ })).toBeVisible();
    await expect(
      page.getByRole("cell", { name: "Motor 01", exact: true }).first(),
    ).toBeVisible();
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export CSV" }).click();
    expect((await download).suggestedFilename()).toContain(`forge-${kind}`);
  }
  await page.screenshot({
    path: "../docs/ui-reports-desktop.png",
    fullPage: true,
  });
});

test("operator browser lists existing users and persists role assignment", async ({
  page,
}) => {
  await login(page, "OPERATOR");
  await page.getByRole("link", { name: "Team" }).click();
  await expect(
    page.getByText("akshay.kripalani74@nmims.in", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("collegeproject@akshaykripalani.com", { exact: true }),
  ).toBeVisible();
  const target = page
    .getByRole("row")
    .filter({ hasText: process.env.CCPROJ_VIEWER_EMAIL! });
  try {
    await target
      .getByRole("checkbox", { name: "operator", exact: true })
      .check();
    await target.getByRole("button", { name: "Save roles" }).click();
    await expect(
      target.getByRole("button", { name: "Save roles" }),
    ).toBeDisabled();
    await page.reload();
    await expect(
      target.getByRole("checkbox", { name: "operator", exact: true }),
    ).toBeChecked();
  } finally {
    await target
      .getByRole("checkbox", { name: "operator", exact: true })
      .uncheck();
    await target.getByRole("button", { name: "Save roles" }).click();
    await expect(
      target.getByRole("button", { name: "Save roles" }),
    ).toBeDisabled();
  }
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});
