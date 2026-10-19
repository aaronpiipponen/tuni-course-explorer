/**
 * The Settings tab: the configuration editor, the feature switches and the maintenance panels.
 *
 * The tab owns the coordination between the two panels that write `config/web.toml`: a saved switch
 * notifies the editor so the key's saved value follows the acknowledgement, and an editor save of
 * that file reloads the switches. Every other panel owns its own read and its own explicit action,
 * and the tab forwards the shell's callback that ends the console's protected session after a
 * successful administration rebuild.
 */
import { useState } from "react";
import type { ServerStatusReport } from "../../api/types";
import type { SessionAccess } from "../../shared/StagePanel";
import type { PanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";
import { Backups } from "./Backups";
import { Configuration } from "./Configuration";
import { Dataset } from "./Dataset";
import { FeatureSwitches } from "./FeatureSwitches";
import { Rebuild } from "./Rebuild";
import { WorkerProvisioning } from "./WorkerProvisioning";

/** Render the Settings tab. */
export function Settings({
  session,
  onRefusal,
  onAdminRebuild,
  dashboard,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
  onAdminRebuild: () => void;
  dashboard: PanelRead<ServerStatusReport>;
}) {
  const [notice, setNotice] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [webUpdate, setWebUpdate] = useState<{
    key: string;
    value: boolean;
  } | null>(null);
  return (
    <div>
      {notice === null ? null : <p className="note">{notice}</p>}
      <div className="grid">
        <Configuration
          session={session}
          onRefusal={onRefusal}
          webUpdate={webUpdate}
          onWebSaved={() => setRevision((current) => current + 1)}
        />
      </div>
      <div className="grid">
        <Dataset
          session={session}
          onRefusal={onRefusal}
          dashboard={dashboard}
        />
        <Backups session={session} onRefusal={onRefusal} />
        <Rebuild
          session={session}
          onRefusal={onRefusal}
          onAdminRebuild={onAdminRebuild}
        />
        <WorkerProvisioning session={session} onRefusal={onRefusal} />
        <FeatureSwitches
          session={session}
          onRefusal={onRefusal}
          revision={revision}
          onSaved={(key, value) => {
            setWebUpdate({ key, value });
            setNotice(
              wording.settings.switchSaved
                .replace("{key}", key)
                .replace("{state}", value ? wording.on : wording.off),
            );
          }}
        />
      </div>
    </div>
  );
}
