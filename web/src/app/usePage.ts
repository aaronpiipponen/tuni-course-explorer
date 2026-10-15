/** Two-path app/docs history state, independent from the persistent browser profile. */
import { useCallback, useEffect, useLayoutEffect, useState } from "react";

export function usePage(): {
  page: "app" | "docs";
  entranceKey: number;
  navigate: (page: "app" | "docs") => void;
} {
  const [page, setPage] = useState<"app" | "docs">(() =>
    location.pathname === "/docs" ? "docs" : "app",
  );
  const [entranceKey, setEntranceKey] = useState(0);
  useLayoutEffect(() => {
    document.documentElement.classList.toggle("app-active", page === "app");
    return () => document.documentElement.classList.remove("app-active");
  }, [page]);
  const navigate = useCallback(
    (next: "app" | "docs") => {
      if (next === page) return;
      history.pushState({}, "", next === "docs" ? "/docs" : "/");
      setPage(next);
      if (page === "docs" && next === "app") setEntranceKey((key) => key + 1);
    },
    [page],
  );
  useEffect(() => {
    const pop = () => {
      const next = location.pathname === "/docs" ? "docs" : "app";
      setPage((previous) => {
        if (previous === "docs" && next === "app")
          setEntranceKey((key) => key + 1);
        return next;
      });
    };
    const show = () => {
      if (location.pathname !== "/docs") setEntranceKey((key) => key + 1);
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
