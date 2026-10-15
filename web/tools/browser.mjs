/** Sole headless Chromium launcher for browser acceptance tooling. */
import { chromium } from "playwright";

export function launchBrowser() {
  return chromium.launch({ headless: true });
}
