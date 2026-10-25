/** Sole headless Chromium launcher for browser acceptance tooling. */
import { chromium } from "playwright";

/** Launch one headless Chromium browser. */
export function launchBrowser() {
  return chromium.launch({ headless: true });
}
