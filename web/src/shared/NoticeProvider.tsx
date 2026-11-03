/** One app-level owner of the notices that each tab pane renders for itself. */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { getActiveTab } from "../app/sessionTab";
import type { DisplayLanguage } from "../state/types";
import {
  NoticeContext,
  NoticeListContext,
  type Notice,
  type NoticeAction,
  type NoticeApi,
  type NoticeOptions,
} from "./noticeContext";

const NOTICE_MS = 2200;

/** Provide the app-level notices to its children. */
export function NoticeProvider({ children }: { children: ReactNode }) {
  const [notices, setNotices] = useState<Notice[]>([]);
  const nextId = useRef(0);
  const timers = useRef(new Map<number, number>());

  const remove = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) {
      window.clearTimeout(timer);
      timers.current.delete(id);
    }
    setNotices((current) => current.filter((notice) => notice.id !== id));
  }, []);

  const dismiss = useCallback((key: string) => {
    setNotices((current) => {
      const match = current.find((notice) => notice.key === key);
      if (!match) return current;
      const timer = timers.current.get(match.id);
      if (timer !== undefined) {
        window.clearTimeout(timer);
        timers.current.delete(match.id);
      }
      return current.filter((notice) => notice.id !== match.id);
    });
  }, []);

  const show = useCallback(
    (
      text: (language: DisplayLanguage) => string,
      action?: NoticeAction,
      options: NoticeOptions = {},
    ) => {
      const id = nextId.current++;
      setNotices((current) => {
        if (options.key !== undefined) {
          const existing = current.find((notice) => notice.key === options.key);
          if (existing) {
            return current.map((notice) =>
              notice.id === existing.id
                ? {
                    ...notice,
                    text,
                    action,
                    link: options.link,
                    persistent: options.persistent ?? false,
                    tab: getActiveTab(),
                  }
                : notice,
            );
          }
        }
        return [
          ...current,
          {
            id,
            text,
            action,
            link: options.link,
            key: options.key,
            persistent: options.persistent ?? false,
            tab: getActiveTab(),
          },
        ];
      });
    },
    [],
  );

  // A new transient notice starts its own timer, and a persistent one carries none.
  useEffect(() => {
    for (const notice of notices) {
      if (notice.persistent || timers.current.has(notice.id)) continue;
      timers.current.set(
        notice.id,
        window.setTimeout(() => remove(notice.id), NOTICE_MS),
      );
    }
  }, [notices, remove]);

  useEffect(
    () => () => {
      for (const timer of timers.current.values()) window.clearTimeout(timer);
      timers.current.clear();
    },
    [],
  );

  const api = useMemo<NoticeApi>(() => ({ show, dismiss }), [dismiss, show]);

  return (
    <NoticeContext.Provider value={api}>
      <NoticeListContext.Provider value={notices}>
        {children}
      </NoticeListContext.Provider>
    </NoticeContext.Provider>
  );
}
