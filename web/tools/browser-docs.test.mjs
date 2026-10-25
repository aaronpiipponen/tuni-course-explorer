/** Real-browser proof that a configured wiki page opens and the return control restores the app. */
import assert from "node:assert/strict";
import test from "node:test";
import { openBrowserSession } from "./browser-fixture.mjs";

test(
  "opens a configured wiki page and returns to the app",
  { timeout: 90000 },
  async () => {
    const { browser, context, page, baseUrl, pageErrors } =
      await openBrowserSession();
    try {
      await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
      await page.locator(".app-shell").waitFor({ state: "visible" });
      await page.locator(".docs-link").click();
      await page.waitForFunction(() => location.pathname === "/docs");
      await page.locator(".docs-shell").waitFor({ state: "visible" });

      await page.locator('.docs-cards a[href="/docs#quickstart"]').click();
      await page.waitForFunction(() => location.hash === "#quickstart");
      await page.waitForFunction(
        () =>
          document.querySelector(".docs-layout main article h1")
            ?.textContent === "Quickstart",
      );
      const article = page.locator(".docs-layout main article h1");
      assert.equal(await article.innerText(), "Quickstart");
      assert.equal(
        await page.locator(".docs-pn a.previous").getAttribute("href"),
        "/docs#home",
      );
      assert.equal(
        await page.locator(".docs-pn a.next").getAttribute("href"),
        "/docs#guide-search",
      );

      await page.evaluate(() => {
        location.hash = "not-a-page";
      });
      const missing = page.locator(".docs-layout main article h1");
      await missing.waitFor({ state: "visible" });
      await page.waitForFunction(
        () =>
          document.querySelector(".docs-layout main article h1")
            ?.textContent === "Page not found",
      );
      assert.equal(await page.locator(".docs-pn").count(), 0);

      await page.locator(".docs-button.primary").click();
      await page.waitForFunction(() => location.pathname === "/");
      await page.locator(".app-shell").waitFor({ state: "visible" });
      assert.deepEqual(pageErrors, []);
    } finally {
      await context.close();
      await browser.close();
    }
  },
);
