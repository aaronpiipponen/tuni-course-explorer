/** Shared browser session, app seed and touch gesture helpers for the real-browser journeys. */
import { launchBrowser } from "./browser.mjs";

const STORAGE_KEY = "tuni-course-explorer";
const ACTIVE_TAB_KEY = "tuni-course-explorer-active-tab";
const LOOPBACK_HOST = "127.0.0.1";

/**
 * Open one isolated Chromium context against the runner's loopback origin.
 *
 * The base address comes from `BROWSER_BASE_URL` and must be a plain HTTP loopback origin. A phone
 * session uses the 390 by 844 viewport, scale factor 2 and touch input. Page errors are collected
 * from this call onward, so a caller reads them after its journey.
 */
export async function openBrowserSession({ phone = false } = {}) {
  const configured = process.env.BROWSER_BASE_URL;
  if (!configured) throw new Error("BROWSER_BASE_URL is required");
  const origin = new URL(configured);
  if (origin.protocol !== "http:" || origin.hostname !== LOOPBACK_HOST)
    throw new Error("BROWSER_BASE_URL must be a loopback HTTP origin");
  const browser = await launchBrowser();
  const context = await browser.newContext(
    phone
      ? {
          viewport: { width: 390, height: 844 },
          deviceScaleFactor: 2,
          isMobile: true,
          hasTouch: true,
          reducedMotion: "reduce",
        }
      : {
          viewport: { width: 1440, height: 900 },
          reducedMotion: "reduce",
        },
  );
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error));
  return { browser, context, page, baseUrl: origin.origin, pageErrors };
}

/**
 * Seed one fresh app context with the chosen open tab and optional prerequisite root.
 *
 * The first visit creates the saved envelope through the app owner. Only the current profile's
 * language and prerequisite root are changed, then the app reloads on the chosen tab.
 */
export async function seedApp(
  page,
  baseUrl,
  { tab = "search", rootCourseId = null } = {},
) {
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(
    (key) => localStorage.getItem(key) !== null,
    STORAGE_KEY,
  );
  await page.locator(".app-shell").waitFor({ state: "visible" });
  await page.evaluate(
    ({ key, activeTabKey, tab, rootCourseId }) => {
      const envelope = JSON.parse(localStorage.getItem(key));
      const state = envelope.profiles[envelope.currentProfileId].state;
      state.language = "en";
      if (rootCourseId !== null)
        state.prerequisites.rootCourseId = rootCourseId;
      localStorage.setItem(key, JSON.stringify(envelope));
      sessionStorage.setItem(activeTabKey, tab);
    },
    {
      key: STORAGE_KEY,
      activeTabKey: ACTIVE_TAB_KEY,
      tab,
      rootCourseId,
    },
  );
  await page.reload({ waitUntil: "domcontentloaded" });
  await page
    .locator(`.tab-pane:not(.exiting)[data-tab="${tab}"]`)
    .waitFor({ state: "visible" });
}

/**
 * Dispatch one real touch drag with ten interpolated moves spaced 16 ms apart.
 *
 * Coordinates are viewport CSS pixels from the target element's live bounding box. The CDP session
 * is detached on every outcome.
 */
export async function touchDrag(context, page, { fromX, fromY, toX, toY }) {
  const session = await context.newCDPSession(page);
  try {
    await session.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [{ x: fromX, y: fromY }],
    });
    for (let step = 1; step <= 10; step += 1) {
      await page.waitForTimeout(16);
      const ratio = step / 10;
      await session.send("Input.dispatchTouchEvent", {
        type: "touchMove",
        touchPoints: [
          {
            x: fromX + (toX - fromX) * ratio,
            y: fromY + (toY - fromY) * ratio,
          },
        ],
      });
    }
    await page.waitForTimeout(16);
    await session.send("Input.dispatchTouchEvent", {
      type: "touchEnd",
      touchPoints: [],
    });
  } finally {
    await session.detach();
  }
}
