/** Native hash-route reader for docs pages and real heading anchors. */
import { useEffect, useState } from "react";
import { isDocsPageId, type DocsPageId } from "./registry";

function readRoute(): { pageId: DocsPageId | null; anchor: string | null } {
  const [page = "home", anchor] = location.hash.slice(1).split("/", 2);
  const decodedPage = decodeURIComponent(page || "home");
  return {
    pageId: isDocsPageId(decodedPage) ? decodedPage : null,
    anchor: anchor ? decodeURIComponent(anchor) : null,
  };
}

export function useDocsRoute(): {
  pageId: DocsPageId | null;
  anchor: string | null;
} {
  const [route, setRoute] = useState(readRoute);
  useEffect(() => {
    const update = () => setRoute(readRoute());
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return route;
}
