/**
 * The test-only DOM boundary of the administration console.
 *
 * jsdom performs no layout, so the panel body measurement gets one no-op `ResizeObserver` substitute
 * that emits no measurement.
 */
import { beforeEach } from "vitest";

class NoopResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

beforeEach(() => {
  globalThis.ResizeObserver =
    NoopResizeObserver as unknown as typeof ResizeObserver;
  window.sessionStorage.clear();
});
