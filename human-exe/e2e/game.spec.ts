import { test, expect } from "@playwright/test";
test("birth, decisions, every screen, persistence, import and mobile", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByLabel("Мне есть 18.").check();
  await page.getByRole("button", { name: "РОДИТЬСЯ" }).click();
  await expect(page.locator(".choices button").first()).toBeVisible();
  expect(await page.locator(".choices button").count()).toBeGreaterThanOrEqual(
    3,
  );
  const name = await page.locator(".character h2").textContent();
  await page.locator(".choices button").first().click();
  await expect(page.locator(".identity b")).toHaveText("1 год");
  await page.waitForTimeout(200);
  await page.reload();
  await expect(page.locator(".character h2")).toHaveText(name!);
  await expect(page.locator(".identity b")).toHaveText("1 год");
  for (const tab of [
    "Карьера",
    "Имущество",
    "Связи",
    "История",
    "Статистика",
    "Достижения",
    "Настройки",
  ]) {
    await page.getByRole("button", { name: tab, exact: true }).click();
    await expect(page.locator(".content-panel")).toBeVisible();
  }
  await page.getByRole("button", { name: "↓ Сохранить", exact: true }).click();
  await expect(page.getByRole("status").first()).toContainText("Сохранено");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "↗ Экспорт JSON" }).click();
  const download = await downloadPromise;
  const path = await download.path();
  expect(path).toBeTruthy();
  await page.locator("input[type=file]").setInputFiles(path!);
  await expect(page.getByRole("status").first()).toContainText(
    "Жизнь восстановлена",
  );
  await page
    .locator("input[type=file]")
    .setInputFiles({
      name: "broken.json",
      mimeType: "application/json",
      buffer: Buffer.from('{"version":1}'),
    });
  await expect(page.getByRole("status").first()).toContainText("повреждено");
  await page.getByRole("button", { name: "Закрыть уведомление" }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Жизнь", exact: true }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await expect(page.locator(".choices button").first()).toBeVisible();
  await page.waitForTimeout(800);
  await page.screenshot({ path: "/tmp/human-exe-mobile.png", fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: "/tmp/human-exe-desktop.png", fullPage: true });
  expect(errors).toEqual([]);
});
test("career, loan, property, family memory and a completed life", async ({
  page,
}) => {
  test.setTimeout(60000);
  await page.goto("/");
  await page.getByLabel("Мне есть 18.").check();
  await page.getByRole("button", { name: "РОДИТЬСЯ" }).click();
  for (let i = 0; i < 18; i++)
    await page
      .locator(".quick-grid button")
      .filter({ hasText: "Отдохнуть" })
      .click();
  await page.getByRole("button", { name: "Карьера", exact: true }).click();
  const job = page
    .locator(".item-card")
    .filter({
      has: page.getByRole("heading", { name: "Кассир", exact: true }),
    });
  await job.getByRole("button").click();
  await expect(page.locator(".job-badge")).toContainText("Кассир");
  await page.getByRole("button", { name: "Имущество", exact: true }).click();
  await page.getByRole("button", { name: "Кредит +100 000 ₽" }).click();
  await expect(page.locator(".balance")).toContainText("Долг");
  const cat = page
    .locator(".item-card")
    .filter({
      has: page.getByRole("heading", {
        name: "Кот с дипломом экономиста",
        exact: true,
      }),
    });
  await cat.getByRole("button").click();
  await expect(cat.getByRole("button")).toHaveText("✓ В собственности");
  await page.getByRole("button", { name: "Связи", exact: true }).click();
  await page.getByRole("button", { name: "ВЫЙТИ К ЛЮДЯМ" }).click();
  await expect(page.locator(".item-card").first()).toContainText(
    "Вы нашли время",
  );
  await page.getByRole("button", { name: "Жизнь", exact: true }).click();
  for (let i = 0; i < 90 && (await page.locator(".death").count()) === 0; i++)
    await page
      .locator(".quick-grid button")
      .filter({ hasText: "Отдохнуть" })
      .click();
  await expect(page.locator(".death")).toBeVisible();
  await expect(page.locator(".death h2")).not.toBeEmpty();
  await page.getByRole("button", { name: "История", exact: true }).click();
  await expect(page.locator(".timeline article").first()).toBeVisible();
  await page.reload();
  await expect(page.locator(".death")).toBeVisible();
});
