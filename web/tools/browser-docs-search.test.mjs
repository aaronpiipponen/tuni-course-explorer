/** Real-browser proof that the wiki search reaches a configured page by title and by body text. */
import assert from "node:assert/strict";
import test from "node:test";
import { openBrowserSession } from "./browser-fixture.mjs";

test(
  "reaches a configured wiki page through the search",
  { timeout: 90000 },
  async () => {
    const { browser, context, page, baseUrl, pageErrors } =
      await openBrowserSession();
    try {
      await page.goto(`${baseUrl}/docs#home`, {
        waitUntil: "domcontentloaded",
      });
      await page.locator(".docs-shell").waitFor({ state: "visible" });
      const input = page.locator(".docs-search input");
      const article = page.locator(".docs-layout main article h1");

      await input.fill("gLoSsArY");
      const glossary = page.locator(
        '.docs-results.open a[href="/docs#glossary"]',
      );
      await glossary.waitFor({ state: "visible" });
      await glossary.click();
      await page.waitForFunction(
        () =>
          document.querySelector(".docs-layout main article h1")
            ?.textContent === "Glossary",
      );
      assert.equal(await article.innerText(), "Glossary");

      await page.locator(".docs-home-link").click();
      await page.waitForFunction(() => location.hash === "#home");
      await page.locator(".docs-hero h1").waitFor({ state: "visible" });

      // The glossary body holds Unembeddable course, which a body-text query finds.
      await input.fill("uNeMbEdDaBlE cOuRsE");
      const unembeddable = page.locator(
        '.docs-results.open a[href="/docs#glossary"]',
      );
      await unembeddable.waitFor({ state: "visible" });
      await unembeddable.click();
      await page.waitForFunction(
        () =>
          document.querySelector(".docs-layout main article h1")
            ?.textContent === "Glossary",
      );
      assert.equal(await article.innerText(), "Glossary");
      assert.deepEqual(pageErrors, []);
    } finally {
      await context.close();
      await browser.close();
    }
  },
);
