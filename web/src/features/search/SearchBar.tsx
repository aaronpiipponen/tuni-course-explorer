/** Explicit-submit growing search field and activity scope control. */
import { useLayoutEffect, useRef } from "react";
import { ActivitySwitch } from "../../shared/ActivitySwitch";
import { useWording } from "../../shared/useWording";

export function SearchBar({
  query,
  activeOnly,
  loading,
  onQueryChange,
  onActiveOnlyChange,
  onSubmit,
}: {
  query: string;
  activeOnly: boolean;
  loading: boolean;
  onQueryChange: (query: string) => void;
  onActiveOnlyChange: (activeOnly: boolean) => void;
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
      className="search-bar bar"
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
        placeholder={t("Search by code, name or topic")}
        onChange={(event) => onQueryChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.nativeEvent.isComposing) {
            event.preventDefault();
            onSubmit();
          }
        }}
      />
      <ActivitySwitch activeOnly={activeOnly} onChange={onActiveOnlyChange} />
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
