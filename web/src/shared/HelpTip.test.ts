/** Rendered proof that help content carries its links inside headings, terms and text. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { StoreContext } from "../state/context";
import { createBrowserStore, type BrowserStore } from "../state/store";
import { HelpLink, HelpTip } from "./HelpTip";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

describe("help link placement", () => {
  let container: HTMLDivElement;
  let root: Root;
  let store: BrowserStore;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    container = document.createElement("div");
    document.body.appendChild(container);
    store = createBrowserStore(localStorage);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    document
      .querySelectorAll(".help-drawer")
      .forEach((drawer) => drawer.remove());
  });

  it("renders heading, term and text links inside the drawer", () => {
    act(() =>
      root.render(
        createElement(
          StoreContext.Provider,
          { value: store },
          createElement(HelpTip, {
            title: "Synthetic help",
            sections: [
              {
                heading: createElement(HelpLink, {
                  href: "/docs#synthetic-heading",
                  children: "Synthetic heading",
                }),
                items: [
                  {
                    term: createElement(HelpLink, {
                      href: "/docs#synthetic-term",
                      children: "Synthetic term",
                    }),
                    text: createElement(
                      "span",
                      null,
                      "Read the ",
                      createElement(HelpLink, {
                        href: "/docs#synthetic-text",
                        children: "synthetic guide",
                      }),
                      " before continuing.",
                    ),
                  },
                ],
              },
            ],
          }),
        ),
      ),
    );

    const trigger = container.querySelector<HTMLButtonElement>(".help-tip");
    if (!trigger) throw new Error("The help trigger is missing");
    act(() => trigger.click());

    const drawer = document.querySelector(".help-drawer");
    if (!drawer) throw new Error("The help drawer is missing");
    expect(
      [...drawer.querySelectorAll("a")].map((link) =>
        link.getAttribute("href"),
      ),
    ).toEqual([
      "/docs#synthetic-heading",
      "/docs#synthetic-term",
      "/docs#synthetic-text",
    ]);
    expect(drawer.querySelector("h3 a")).toBeTruthy();
    expect(drawer.querySelector("dt a")).toBeTruthy();
    expect(drawer.querySelector("dd a")).toBeTruthy();
  });
});
