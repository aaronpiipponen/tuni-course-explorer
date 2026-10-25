/** Real-browser proof that the served graph finds and clears one minimum route in a worker. */
import assert from "node:assert/strict";
import test from "node:test";
import { openBrowserSession, seedApp } from "./browser-fixture.mjs";

test(
  "finds and clears a minimum route in the served app",
  { timeout: 90000 },
  async () => {
    const { browser, context, page, baseUrl, pageErrors } =
      await openBrowserSession();
    try {
      await seedApp(page, baseUrl, {
        tab: "prerequisites",
        rootCourseId: "mock-observation",
      });
      await page.locator(".routebox .rbtn").waitFor({ state: "visible" });
      await page.waitForFunction(() => {
        const button = document.querySelector(".routebox .rbtn");
        return button !== null && button.disabled === false;
      });
      assert.equal(await page.locator(".route-panel.open").count(), 0);

      const workers = [];
      page.on("worker", (worker) => workers.push(worker));
      await page.locator(".routebox .rbtn").click();
      await page
        .locator(".route-panel.open .route-tag")
        .waitFor({ state: "visible" });
      await page.waitForFunction(() => {
        const panel = document.querySelector(".route-panel.open");
        const total = panel?.querySelector(".route-total");
        return (
          total !== null &&
          total !== undefined &&
          total.textContent.trim() !== "" &&
          panel.querySelector(".route-spinner") === null &&
          panel.querySelector(".route-error") === null
        );
      });
      assert.equal(workers.length >= 1, true, "the route runs in a worker");

      await page.locator(".route-panel.open .route-expand").click();
      const row = page.locator(".route-panel.open .route-row").first();
      await row.waitFor({ state: "visible" });
      const rowText = await row.innerText();
      assert.match(rowText, /DEMO\./);

      await page.locator(".routebox .rbtn.on").click();
      await page.waitForFunction(
        () => document.querySelector(".route-panel.open") === null,
      );
      await page.waitForFunction(() => {
        const button = document.querySelector(".routebox .rbtn");
        return (
          button !== null &&
          button.disabled === false &&
          !button.classList.contains("on")
        );
      });
      assert.deepEqual(pageErrors, []);
    } finally {
      await context.close();
      await browser.close();
    }
  },
);
