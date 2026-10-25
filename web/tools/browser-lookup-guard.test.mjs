/** Real-browser proof that a touch scroll over a lookup row picks nothing and a tap picks it. */
import assert from "node:assert/strict";
import test from "node:test";
import { openBrowserSession, seedApp, touchDrag } from "./browser-fixture.mjs";

/** Read the two saved comparison slots from the stored envelope. */
function readSlots(page) {
  return page.evaluate(() => {
    const envelope = JSON.parse(localStorage.getItem("tuni-course-explorer"));
    return envelope.profiles[envelope.currentProfileId].state.compare.slots;
  });
}

test(
  "keeps a touch scroll from picking a lookup row",
  { timeout: 90000 },
  async () => {
    const { browser, context, page, baseUrl, pageErrors } =
      await openBrowserSession({ phone: true });
    try {
      await seedApp(page, baseUrl, { tab: "compare" });
      assert.deepEqual(await readSlots(page), [null, null]);
      await page
        .getByRole("button", { name: "Choose course A", exact: true })
        .click();
      const overlay = page.locator(".compare-picker-overlay.open");
      await overlay.waitFor({ state: "visible" });
      const filter = page.locator(
        ".compare-picker-panel .course-lookup-controls input",
      );
      await filter.fill("DEMO");
      const rows = page.locator(".lookup-virtual-row .prow");
      await rows.first().waitFor({ state: "visible" });

      const listBox = await page.locator(".course-lookup-list").boundingBox();
      const dragStart = await page.evaluate(() => {
        const list = document.querySelector(".course-lookup-list");
        if (list === null) return null;
        const bounds = list.getBoundingClientRect();
        const rows = [...list.querySelectorAll(".lookup-virtual-row")].filter(
          (row) => {
            const box = row.getBoundingClientRect();
            return box.top >= bounds.top + 2 && box.bottom <= bounds.bottom - 2;
          },
        );
        const button = rows.at(-1)?.querySelector(".prow");
        if (button === undefined) return null;
        const box = button.getBoundingClientRect();
        return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
      });
      if (listBox === null || dragStart === null)
        throw new Error("The lookup row has no box");
      const toY = Math.max(listBox.y + 4, dragStart.y - 200);
      await touchDrag(context, page, {
        fromX: dragStart.x,
        fromY: dragStart.y,
        toX: dragStart.x,
        toY,
      });
      await page.evaluate(
        () =>
          new Promise((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(resolve)),
          ),
      );

      assert.equal(await overlay.count(), 1);
      assert.deepEqual(await readSlots(page), [null, null]);

      const target = await page.evaluate(() => {
        const list = document.querySelector(".course-lookup-list");
        if (list === null) return null;
        const bounds = list.getBoundingClientRect();
        for (const row of list.querySelectorAll(".lookup-virtual-row")) {
          const box = row.getBoundingClientRect();
          if (box.top < bounds.top + 2 || box.bottom > bounds.bottom - 2)
            continue;
          const button = row.querySelector(".prow");
          const code = button?.querySelector(".code")?.textContent ?? "";
          return { key: row.getAttribute("data-key"), code };
        }
        return null;
      });
      if (target === null || target.key === null)
        throw new Error("No visible lookup row");
      const row = page.locator(
        `.lookup-virtual-row[data-key="${target.key}"] .prow`,
      );
      await row.tap();

      await page.waitForFunction(
        () => document.querySelector(".compare-picker-overlay.open") === null,
      );
      await page.waitForFunction((key) => {
        const envelope = JSON.parse(
          localStorage.getItem("tuni-course-explorer"),
        );
        const slots =
          envelope.profiles[envelope.currentProfileId].state.compare.slots;
        return slots[0] === key && slots[1] === null;
      }, target.key);
      const card = page.locator('[data-slot="0"] .compare-slot-card');
      await card.waitFor({ state: "visible" });
      await page.waitForFunction(
        (code) =>
          document
            .querySelector('[data-slot="0"] .compare-slot-card')
            ?.innerText.includes(code) === true,
        target.code,
      );
      assert.equal((await card.innerText()).includes(target.code), true);
      assert.deepEqual(pageErrors, []);
    } finally {
      await context.close();
      await browser.close();
    }
  },
);
