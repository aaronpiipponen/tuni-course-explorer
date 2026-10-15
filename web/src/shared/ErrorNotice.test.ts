/** Failure presentation: one localized summary on re-render, with diagnostics shown. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ApiError } from "../api/http";
import { ErrorNotice } from "./ErrorNotice";
import { uiText } from "./wording";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

describe("error notice", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("re-renders a visible failure in the supplied language while retaining diagnostics", () => {
    const error = new ApiError("transport detail from the boundary", 503);
    act(() =>
      root.render(createElement(ErrorNotice, { error, language: "en" })),
    );
    const english = container.innerHTML;
    act(() =>
      root.render(createElement(ErrorNotice, { error, language: "fi" })),
    );
    const finnish = container.innerHTML;

    for (const [markup, language] of [
      [english, "en"],
      [finnish, "fi"],
    ] as const) {
      expect(markup).toContain('role="alert"');
      expect(markup).toContain(
        uiText(language, "Request failed ({status})", { status: 503 }),
      );
      // The technical message carries verbatim under the localized label.
      expect(markup).toContain(uiText(language, "Original technical detail"));
      expect(markup).toContain("transport detail from the boundary");
    }
    expect(english).not.toBe(finnish);
  });
});
