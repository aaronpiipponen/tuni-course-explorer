/**
 * The administration console shell: one in-memory session and its admission transitions.
 *
 * The shell loads the session once and shows its sign-in screen while the session is anonymous. An
 * authenticated session mounts the signed-in console, which holds every tab tree at once and hides
 * the inactive ones, so each tab's reports live in browser memory for the signed-in session and a
 * tab switch opens retained data without another read. Every refused request follows one admission
 * policy: a protected 401 clears the protected state and returns to sign-in through one bootstrap,
 * and the lock's bare 403 clears the state and renders an empty root. The protected tabs exist only
 * while the session is authenticated, so signing out, a refusal, a completed administration rebuild
 * or a lost session unmounts the whole subtree and cancels its reads. One refusal per authenticated
 * session is enough, so concurrent refusals from the mounted trees share one re-bootstrap. A
 * completed administration rebuild clears the session without a bootstrap, because the backend that
 * holds the sessions is about to restart, and its sign-in screen reads a fresh session when it is
 * submitted.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchSession, logout } from "../api/auth";
import { ApiError, failureText, handleAdmissionFailure } from "../api/http";
import type { SessionReport } from "../api/types";
import { FailureNotice } from "../shared/Panel";
import { wording } from "../shared/wording";
import { SignIn } from "./SignIn";
import { SignedInConsole } from "./SignedInConsole";

/** Render the administration console. */
export function App() {
  const [session, setSession] = useState<SessionReport | null>(null);
  const [locked, setLocked] = useState(false);
  const [adminRebuilt, setAdminRebuilt] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const refused = useRef(false);

  const bootstrap = useCallback(async (): Promise<void> => {
    try {
      setSession(await fetchSession());
      setLocked(false);
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setSession(null);
        setFailure(null);
        setLocked(true);
        return;
      }
      setFailure(wording.signIn.unavailable);
    }
  }, []);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  useEffect(() => {
    // A granted session is a fresh admission attempt of its own, whatever ended the previous one.
    if (session?.authenticated === true) {
      refused.current = false;
    }
  }, [session]);

  const onRefusal = useCallback(
    (status: number): void => {
      if (refused.current) {
        return;
      }
      refused.current = true;
      setSession(null);
      setFailure(null);
      if (status === 403) {
        setLocked(true);
        return;
      }
      void bootstrap();
    },
    [bootstrap],
  );

  const onSignOut = async (): Promise<void> => {
    if (session === null) {
      return;
    }
    setFailure(null);
    try {
      await logout(session.csrf_token);
    } catch (error) {
      if (handleAdmissionFailure(error, onRefusal)) {
        return;
      }
      setFailure(failureText(error, wording.writeFailed));
      return;
    }
    setSession(null);
    await bootstrap();
  };

  const onAdminRebuild = useCallback((): void => {
    // The answered build is complete and the backend restarts next, so this screen reads no session
    // and a refusal on this anonymous screen is handled like the first one.
    refused.current = false;
    setFailure(null);
    setSession(null);
    setAdminRebuilt(true);
  }, []);

  const onAuthenticated = useCallback((report: SessionReport): void => {
    setAdminRebuilt(false);
    setSession(report);
  }, []);

  if (locked) {
    return null;
  }
  if (adminRebuilt) {
    return (
      <div>
        <SignIn
          session={null}
          onAuthenticated={onAuthenticated}
          onRefusal={onRefusal}
        />
        <p className="note">{wording.settings.adminRebuilt}</p>
      </div>
    );
  }
  if (session === null) {
    return <div className="boot">{failure ?? wording.reading}</div>;
  }
  if (!session.authenticated) {
    return (
      <div>
        <FailureNotice text={failure} />
        <SignIn
          session={session}
          onAuthenticated={onAuthenticated}
          onRefusal={onRefusal}
        />
      </div>
    );
  }

  return (
    <SignedInConsole
      session={session}
      onRefusal={onRefusal}
      onSignOut={onSignOut}
      onAdminRebuild={onAdminRebuild}
      failure={failure}
    />
  );
}
