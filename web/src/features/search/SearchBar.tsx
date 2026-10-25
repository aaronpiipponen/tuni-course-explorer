/** Explicit-submit growing search field with a caller-supplied activity slot. */
import { useLayoutEffect, useRef, type ReactNode } from "react";
import { useWording } from "../../shared/useWording";

/** Render the search field that submits on Enter and grows with its text. */
export function SearchBar({
  query,
  loading,
  phone,
  activity,
  onQueryChange,
  onSubmit,
}: {
  query: string;
  loading: boolean;
  phone: boolean;
  activity?: ReactNode;
  onQueryChange: (query: string) => void;
  onSubmit: () => void;
}) {
  const textarea = useRef<HTMLTextAreaElement>(null);
  const { t } = useWording();
  useLayoutEffect(() => {
    const resize = () => {
      const field = textarea.current;
      if (!field) return;
      field.style.height = "auto";
      field.style.height = `${field.scrollHeight}px`;
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [query]);
  return (
    <form
      className="search-bar"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.5-3.5" />
      </svg>
      <textarea
        ref={textarea}
        aria-label={t("Search by code, name or topic")}
        value={query}
        rows={1}
        placeholder={t(
          phone ? "Search by code or name" : "Search by code, name or topic",
        )}
        onChange={(event) => onQueryChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.nativeEvent.isComposing) {
            event.preventDefault();
            onSubmit();
          }
        }}
      />
      {activity && <span className="search-inline-activity">{activity}</span>}
      <button
        className="search-submit"
        type="submit"
        aria-label={t("Search")}
        aria-busy={loading}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
      </button>
    </form>
  );
}
