/**
 * Shared mount, query and settle helpers of the Settings dataset panel proofs.
 *
 * The module owns the act environment and the inventory read the Settings tab supplies, so each
 * proof file keeps only its own fixtures, fetch stubs and turn counts.
 */
import { act, createElement } from "react";
import { readDatasets } from "../../api/datasets";
import type { DatasetListReport, ServerStatusReport } from "../../api/types";
import { usePanelRead, type PanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";
import { Datasets } from "./Datasets";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

/** The panel's own admission refusal, which these proofs never drive. */
const onRefusal = (): void => {};

/** Mount the dataset panel over the shared inventory read the Settings tab supplies. */
export function DatasetsHarness({
  session,
  dashboard,
}: {
  session: { csrfToken: string; pollSeconds: number };
  dashboard: PanelRead<ServerStatusReport>;
}) {
  const listing = usePanelRead<DatasetListReport>(
    (signal, automatic) => readDatasets(signal, automatic),
    {
      pollSeconds: session.pollSeconds,
      enabled: true,
      onRefusal,
      failureTextValue: wording.readFailed,
    },
  );
  return createElement(Datasets, {
    session,
    onRefusal,
    dashboard,
    listing,
  });
}

/** Return every button whose visible text is the supplied name. */
export function buttonsNamed(name: string): HTMLButtonElement[] {
  return [...document.body.querySelectorAll("button")].filter(
    (element) => element.textContent?.trim() === name,
  );
}

/** Flush the pending request chain and its state updates over the supplied turn count. */
export async function settle(turns: number): Promise<void> {
  await act(async () => {
    for (let turn = 0; turn < turns; turn += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });
}
