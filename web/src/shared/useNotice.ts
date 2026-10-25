/** Read the app-level transient notice API from its mounted provider. */
import { useContext } from "react";
import { NoticeContext, type NoticeApi } from "./noticeContext";

/**
 * Read the app-level transient notice API from its mounted provider.
 *
 * Throws an `Error` when no notice provider is mounted.
 */
export function useNotice(): NoticeApi {
  const notice = useContext(NoticeContext);
  if (!notice) throw new Error("Notice provider is missing");
  return notice;
}
