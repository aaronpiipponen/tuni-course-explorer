/** Live profile menu trigger and operation owner over the browser store. */
import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useCurrentProfile } from "../../state/useCurrentProfile";
import { useAction } from "../../shared/useAction";
import { useWording } from "../../shared/useWording";
import { usePhoneTabsOnClose } from "../../shared/usePhoneTabsOnClose";
import { PROFILE_NOTICE_MS } from "./ProfileNotice";
import { ProfilePanel } from "./ProfilePanel";

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

/**
 * Render the live profile trigger and its operation owner over the browser store.
 *
 * `onClosedEscape` receives an Escape that reaches the closed profile content while its exit
 * animation keeps it mounted, so the containing sheet can dismiss itself.
 */
export function ProfileButton({
  onClosedEscape,
}: { onClosedEscape?: () => void } = {}) {
  const { store, profile, currentProfileId, profiles } = useCurrentProfile();
  const { t } = useWording();
  const [open, setOpen] = useState(false);
  usePhoneTabsOnClose(open);
  const { runAction, error } = useAction(PROFILE_NOTICE_MS);
  const { runAction: runRename, error: renameError } =
    useAction(PROFILE_NOTICE_MS);
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
        <Dialog.Content
          className="profile-menu"
          aria-describedby={undefined}
          onEscapeKeyDown={() => {
            if (!open) onClosedEscape?.();
          }}
        >
          <div className="profile-menu-inner">
            <Dialog.Title className="profile-title">
              {t("Profiles")}
            </Dialog.Title>
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
              store={store}
            />
          </div>
        </Dialog.Content>
      </div>
    </Dialog.Root>
  );
}
