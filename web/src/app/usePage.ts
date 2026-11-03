/**
 * The app, documentation and feedback paths as browser history state, independent of the persistent
 * browser profile.
 */
import { useCallback, useEffect, useLayoutEffect, useState } from "react";

function resetWindowScroll(): void {
  window.scrollTo(0, 0);
}

function pageAt(pathname: string): "app" | "docs" | "feedback" {
  if (pathname === "/docs") return "docs";
  if (pathname === "/feedback") return "feedback";
  return "app";
}

const PAGE_PATH: Record<"app" | "docs" | "feedback", string> = {
  app: "/",
  docs: "/docs",
  feedback: "/feedback",
};

/** Track app, documentation or feedback navigation and reset the app entrance state. */
export function usePage(): {
  page: "app" | "docs" | "feedback";
  entranceKey: number;
  navigate: (page: "app" | "docs" | "feedback") => void;
} {
  const [page, setPage] = useState<"app" | "docs" | "feedback">(() =>
    pageAt(location.pathname),
  );
  const [entranceKey, setEntranceKey] = useState(0);
  useLayoutEffect(() => {
    document.documentElement.classList.toggle("app-active", page === "app");
    // The shell scrolls its panes inside a document with no page scroll. A window offset the
    // browser keeps when the app opens or is restored puts the shell's top above the screen.
    if (page === "app") resetWindowScroll();
    return () => document.documentElement.classList.remove("app-active");
  }, [page]);
  const navigate = useCallback(
    (next: "app" | "docs" | "feedback") => {
      if (next === page) return;
      history.pushState({}, "", PAGE_PATH[next]);
      setPage(next);
      if (page !== "app" && next === "app") setEntranceKey((key) => key + 1);
    },
    [page],
  );
  useEffect(() => {
    const pop = () => {
      const next = pageAt(location.pathname);
      setPage((previous) => {
        if (previous !== "app" && next === "app")
          setEntranceKey((key) => key + 1);
        return next;
      });
    };
    const show = () => {
      // The app's entrance is the root path alone. A restored documentation or feedback page
      // keeps its own scroll position.
      if (location.pathname === "/") {
        resetWindowScroll();
        setEntranceKey((key) => key + 1);
      }
    };
    window.addEventListener("popstate", pop);
    window.addEventListener("pageshow", show);
    return () => {
      window.removeEventListener("popstate", pop);
      window.removeEventListener("pageshow", show);
    };
  }, []);
  return { page, entranceKey, navigate };
}
