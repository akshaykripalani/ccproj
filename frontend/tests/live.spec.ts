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
  await expect(page.getByText("Healthy", { exact: true })).toHaveCount(7);
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
    path: "../docs/predictive-ui/ui-device-desktop.png",
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
    path: "../docs/predictive-ui/ui-overview-desktop.png",
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
      path: "../docs/predictive-ui/ui-overview-mobile.png",
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

test("browser controls demonstrate automatic cooldown and manual mechanical repair", async ({
  page,
}) => {
  test.setTimeout(420000);
  await login(page, "OPERATOR");
  const first = page.getByTestId("motor-01"),
    second = page.getByTestId("motor-02");
  try {
    await page.locator(".demo-controls > summary").click();
    await page.getByRole("button", { name: "Overheat", exact: true }).click();
    await expect(first.getByText("Fault", { exact: true })).toBeVisible();
    await expect(
      first.getByText("Restarted automatically", { exact: true }),
    ).toBeVisible({ timeout: 150000 });
    await expect(first.getByText("Healthy", { exact: true })).toBeVisible();
    await page
      .getByRole("combobox", { name: "Equipment", exact: true })
      .selectOption("motor-02");
    await page
      .getByRole("button", { name: "Vibration fault", exact: true })
      .click();
    await expect(second.getByText("Fault", { exact: true })).toBeVisible();
    await expect(
      second.getByText("Repair needed", { exact: true }),
    ).toBeVisible();
    await page.getByRole("link", { name: /^Alerts/ }).click();
    await expect(
      page
        .getByRole("row")
        .filter({ hasText: "Motor 02" })
        .filter({ hasText: "active" })
        .first(),
    ).toBeVisible();
    await page.screenshot({
      path: "../docs/predictive-ui/ui-alerts-desktop.png",
      fullPage: true,
    });
    await page.getByRole("link", { name: "Overview", exact: true }).click();
    await second.getByRole("button", { name: "Repair", exact: true }).click();
    await expect(second.getByText("Healthy", { exact: true })).toBeVisible();
    await page.locator(".demo-controls > summary").click();
    await page.getByRole("button", { name: "Disconnect", exact: true }).click();
    await expect(first.getByText("Offline", { exact: true })).toBeVisible();
  } finally {
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
        throw new Error("Final equipment restoration request was rejected");
    });
  }
  await expect(page.getByText("Healthy", { exact: true })).toHaveCount(7);
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
    path: "../docs/predictive-ui/ui-reports-desktop.png",
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

test("new equipment metrics, maintenance history and model details are live", async ({
  page,
}) => {
  await login(page, "OPERATOR");
  await page
    .getByRole("link", { name: "Generator", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Generator", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Generated power", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Frequency", { exact: true })).toBeVisible();
  await expect(page.locator(".prediction-detail small")).toBeVisible();
  await page.getByText("Model details", { exact: false }).click();
  await expect(
    page.getByText("Held-out precision", { exact: false }),
  ).toContainText("90.3%");
  await page.screenshot({
    path: "../docs/predictive-ui/ui-predictive-generator.png",
    fullPage: true,
  });
});
