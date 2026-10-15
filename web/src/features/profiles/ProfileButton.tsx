/** Live profile menu trigger and operation owner over the browser store. */
import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useCurrentProfile } from "../../state/useCurrentProfile";
import { useAction } from "../../shared/useAction";
import { useWording } from "../../shared/useWording";
import { ProfilePanel } from "./ProfilePanel";

const ERROR_SECONDS = 5;

function succeeded(
  run: (action: () => void) => void,
  action: () => void,
): boolean {
  let ok = false;
  run(() => {
    action();
    ok = true;
  });
  return ok;
}

export function ProfileButton() {
  const { store, profile, currentProfileId, profiles } = useCurrentProfile();
  const { t } = useWording();
  const [open, setOpen] = useState(false);
  const { runAction, error } = useAction(ERROR_SECONDS * 1000);
  const { runAction: runRename, error: renameError } = useAction(
    ERROR_SECONDS * 1000,
  );
  const switchProfile = (id: string) =>
    runAction(() => {
      store.switchProfile(id);
      setOpen(false);
    });
  return (
    <Dialog.Root open={open} modal={false} onOpenChange={setOpen}>
      <div className="profile-control">
        <Dialog.Trigger asChild>
          <button
            className="profile-trigger"
            type="button"
            aria-expanded={open}
          >
            <span className="profile-name">{profile.name}</span>
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="m4 6 4 4 4-4" />
            </svg>
          </button>
        </Dialog.Trigger>
        <Dialog.Content className="profile-menu" aria-describedby={undefined}>
          <Dialog.Title className="profile-title">{t("Profiles")}</Dialog.Title>
          <ProfilePanel
            profiles={profiles}
            currentProfileId={currentProfileId}
            onSwitch={switchProfile}
            onDelete={(id) => runAction(() => store.deleteProfile(id))}
            onSaveAs={(name) =>
              succeeded(runAction, () => store.saveAsProfile(name))
            }
            onRename={(id, name) =>
              succeeded(runRename, () => store.renameProfile(id, name))
            }
            error={error}
            renameError={renameError}
          />
        </Dialog.Content>
      </div>
    </Dialog.Root>
  );
}
