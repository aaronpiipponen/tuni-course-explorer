/** Real-browser proof of the phone shell, its swipe navigation and its More sheet. */
import assert from "node:assert/strict";
import test from "node:test";
import { openBrowserSession, seedApp, touchDrag } from "./browser-fixture.mjs";

const TAB_NAMES = [
  "Search",
  "Compare",
  "Prerequisites",
  "Discover",
  "Structure of studies",
];

test(
  "uses the phone shell with swipe navigation and hidden carousel arrows",
  { timeout: 90000 },
  async () => {
    const { browser, context, page, baseUrl, pageErrors } =
      await openBrowserSession({ phone: true });
    try {
      await seedApp(page, baseUrl, { tab: "search" });
      await page.locator(".phone-tabbar").waitFor({ state: "visible" });
      assert.equal(await page.locator(".topbar").isVisible(), false);
      const arrows = page.locator(".carousel-arrow");
      assert.equal(await arrows.count(), 2);
      for (let index = 0; index < 2; index += 1)
        assert.equal(await arrows.nth(index).isVisible(), false);
      for (const name of TAB_NAMES)
        assert.equal(
          await page
            .locator(`.phone-tabbar .phone-tab[aria-label="${name}"]`)
            .count(),
          1,
        );
      assert.equal(
        await page
          .locator(".phone-tabbar .phone-tab", { hasText: "More" })
          .count(),
        1,
      );

      const swipe = async (left) => {
        const pane = page.locator(".tab-pane:not(.exiting)[data-tab]").first();
        const box = await pane.boundingBox();
        if (box === null) throw new Error("The active tab pane has no box");
        const y = box.y + box.height / 2;
        const inset = 8;
        await touchDrag(context, page, {
          fromX: box.x + (left ? box.width - inset : inset),
          fromY: y,
          toX: box.x + (left ? inset : box.width - inset),
          toY: y,
        });
      };

      await swipe(true);
      await page.waitForFunction(
        () =>
          document
            .querySelector(".phone-tabbar .phone-tab.active")
            ?.getAttribute("aria-label") === "Compare",
      );
      await page
        .locator('.tab-pane:not(.exiting)[data-tab="compare"]')
        .waitFor({ state: "visible" });

      await swipe(false);
      await page.waitForFunction(
        () =>
          document
            .querySelector(".phone-tabbar .phone-tab.active")
            ?.getAttribute("aria-label") === "Search",
      );
      await page
        .locator('.tab-pane:not(.exiting)[data-tab="search"]')
        .waitFor({ state: "visible" });

      await page
        .locator(".phone-tabbar .phone-tab", { hasText: "More" })
        .click();
      const sheet = page.locator('.phone-more-sheet[role="dialog"]');
      await sheet.waitFor({ state: "visible" });
      await sheet.locator(".profile-trigger").waitFor({ state: "visible" });
      const languageLabels = await sheet
        .locator(".language-switch span")
        .allInnerTexts();
      assert.deepEqual(languageLabels, ["FI", "EN"]);
      await sheet
        .locator(".phone-more-docs", { hasText: "Docs" })
        .waitFor({ state: "visible" });
      assert.deepEqual(pageErrors, []);
    } finally {
      await context.close();
      await browser.close();
    }
  },
);
