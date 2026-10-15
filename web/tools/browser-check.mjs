/**
 * Inspect a loopback frontend page, fail on page errors, and optionally save a screenshot.
 *
 * Usage: node tools/browser-check.mjs http://127.0.0.1:<port>/ [screenshot.png]
 * page URL: loopback frontend page to load. It must start with `http://127.0.0.1`.
 * screenshot path: optional PNG file path for a full-page screenshot.
 */
import { resolve } from "node:path";
import { launchBrowser } from "./browser.mjs";

async function main() {
  const [, , pageUrl, screenshotPath] = process.argv;
  if (!pageUrl || !/^http:\/\/127\.0\.0\.1(?::\d+)?\//.test(pageUrl)) {
    throw new Error(
      "Usage: node tools/browser-check.mjs http://127.0.0.1:<port>/ [screenshot.png]",
    );
  }
  const browser = await launchBrowser();
  const context = await browser.newContext();
  try {
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error));
    const response = await page.goto(pageUrl, { waitUntil: "networkidle" });
    if (!response?.ok())
      throw new Error(`Page returned ${response?.status() ?? "no response"}`);
    await page.evaluate(() => document.fonts.ready);
    if (errors.length) throw errors[0];
    if (screenshotPath)
      await page.screenshot({
        path: resolve(screenshotPath),
        fullPage: true,
      });
    console.log(
      `Loaded ${pageUrl}${screenshotPath ? `; screenshot ${screenshotPath}` : ""}`,
    );
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
