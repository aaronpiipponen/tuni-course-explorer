/** Poll a rendered test condition while flushing pending React effects between polls. */
import { act } from "react";
import { vi } from "vitest";

/** Wait until the assertion holds, running every poll inside React act. */
export async function waitFor(assertion: () => void): Promise<void> {
  await vi.waitFor(async () => {
    let failure: unknown;
    // React act leaves a rejected async scope unflushed, so the assertion error is thrown only
    // after the act call resolves and its pending effects have run.
    await act(async () => {
      try {
        assertion();
      } catch (caught) {
        failure = caught;
      }
    });
    if (failure !== undefined) {
      throw failure;
    }
  });
}
