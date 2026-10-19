/**
 * The console's sign-in screen.
 *
 * It posts one credential attempt over a live session's CSRF token, clears the password field after
 * every submit, and reports one refusal without retrying the attempt. A supplied session is used as
 * it is, and a missing one is read from the site once, so the screen works after the console's
 * protected session has ended without a bootstrap of its own. A wrong credential stays in the screen
 * as its own message, while a `403` is the terminal admission refusal the shell's handling consumes.
 * A missing live session and a site or CSRF refusal answer that same status.
 */
import { useState, type FormEvent } from "react";
import { ApiError, handleAdmissionFailure } from "../api/http";
import { fetchSession, login } from "../api/auth";
import type { SessionReport } from "../api/types";
import { wording } from "../shared/wording";

/** Render the sign-in screen. */
export function SignIn({
  session,
  onAuthenticated,
  onRefusal,
}: {
  session: SessionReport | null;
  onAuthenticated: (report: SessionReport) => void;
  onRefusal: (status: number) => void;
}) {
  const text = wording.signIn;
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const onSubmit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setPending(true);
    setFailure(null);
    try {
      const active = session ?? (await fetchSession());
      const report = await login(username, password, active.csrf_token);
      setPassword("");
      onAuthenticated(report);
    } catch (error) {
      setPassword("");
      if (error instanceof ApiError && error.status === 403) {
        handleAdmissionFailure(error, onRefusal);
        return;
      }
      setFailure(refusalText(error));
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="login">
      <form
        className="loginbox"
        autoComplete="off"
        onSubmit={(event) => void onSubmit(event)}
      >
        <div className="logo">
          <i>T</i>
          {wording.brand}
        </div>
        <h1>{text.heading}</h1>
        <label className="field">
          <span>{text.username}</span>
          <input
            name="user"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </label>
        <label className="field">
          <span>{text.password}</span>
          <input
            name="pass"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button className="btn p" type="submit" disabled={pending}>
          {text.submit}
        </button>
        <div className="loginerr" role="alert">
          {failure}
        </div>
      </form>
    </div>
  );
}

function refusalText(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return wording.signIn.refused;
  }
  return wording.signIn.failed;
}
