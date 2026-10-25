/** One app-level owner of the transient bottom notice and its optional action. */
import { useEffect, useState, type ReactNode } from "react";
import type { DisplayLanguage } from "../state/types";
import { ErrorNotice } from "./ErrorNotice";
import {
  NoticeContext,
  type NoticeAction,
  type NoticeApi,
} from "./noticeContext";
import { useAction } from "./useAction";
import { useWording } from "./useWording";

const NOTICE_MS = 2200;

/** Provide the app-level transient notice to its children. */
export function NoticeProvider({ children }: { children: ReactNode }) {
  const { language } = useWording();
  const [notice, setNotice] = useState<{
    text: (language: DisplayLanguage) => string;
    action?: NoticeAction;
  } | null>(null);
  const { runAction, error } = useAction();
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), NOTICE_MS);
    return () => window.clearTimeout(timer);
  }, [notice]);
  const show: NoticeApi["show"] = (text, action) =>
    runAction(() => setNotice({ text, action }));
  const action = notice?.action ?? null;
  return (
    <NoticeContext.Provider value={{ show }}>
      {children}
      {notice && (
        <div className="toast" role="status">
          {notice.text(language)}
          {action && (
            <button
              className="toast-action"
              type="button"
              onClick={() => runAction(action.run)}
            >
              {action.label(language)}
            </button>
          )}
        </div>
      )}
      {error && <ErrorNotice error={error} language={language} />}
    </NoticeContext.Provider>
  );
}
