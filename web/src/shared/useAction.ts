/** UI action error boundary: expose storage/action failures to the user. */
import { useEffect, useState } from "react";

/** `clearAfterMs` makes a failure message disappear by itself after that long. */
export function useAction(clearAfterMs?: number): {
  runAction: (action: () => void) => void;
  error: Error | null;
} {
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => {
    if (!error || clearAfterMs === undefined) return;
    const timer = setTimeout(() => setError(null), clearAfterMs);
    return () => clearTimeout(timer);
  }, [error, clearAfterMs]);
  return {
    error,
    runAction(action) {
      try {
        action();
        setError(null);
      } catch (caught) {
        setError(caught instanceof Error ? caught : new Error(String(caught)));
      }
    },
  };
}
