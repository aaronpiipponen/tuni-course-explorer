/** One localized result count shared by the desktop head and the phone secondary row. */
import { useWording } from "../../shared/useWording";

/** Return the result count as the shared slash mark, bold numeral and course word. */
export function SearchCount({ count }: { count: number }) {
  const { t } = useWording();
  return (
    <>
      // <b>{count}</b> {t(count === 1 ? "course" : "courses")}
    </>
  );
}
