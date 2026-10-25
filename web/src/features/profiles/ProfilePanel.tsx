/** Profile list, rename and delete prompts, copy form and file transfer. */
import { useState, type FormEvent } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { AnimatePresence, motion } from "framer-motion";
import type { BrowserState } from "../../state/types";
import type { BrowserStore } from "../../state/store";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { TRASH } from "../../shared/icons";
import { useReducedMotion } from "../../shared/useReducedMotion";
import { useWording } from "../../shared/useWording";
import { usePhoneTabsOnClose } from "../../shared/usePhoneTabsOnClose";
import { ProfileNotice } from "./ProfileNotice";
import { ProfileTransfer } from "./ProfileTransfer";

/** Render the profile list with its rename, delete, copy and file-transfer controls. */
export function ProfilePanel({
  profiles,
  currentProfileId,
  onSwitch,
  onDelete,
  onSaveAs,
  onRename,
  error,
  renameError,
  store,
}: {
  profiles: BrowserState["profiles"];
  currentProfileId: string;
  onSwitch(id: string): void;
  onDelete(id: string): void;
  onSaveAs(name: string): boolean;
  onRename(id: string, name: string): boolean;
  error: Error | null;
  renameError: Error | null;
  store: BrowserStore;
}) {
  const { language, t } = useWording();
  const reducedMotion = useReducedMotion();
  const [name, setName] = useState("");
  // The targets are held after a dialog closes so its content outlasts the close animation.
  const [renameOpen, setRenameOpen] = useState(false);
  const [renaming, setRenaming] = useState("");
  const [renameName, setRenameName] = useState("");
  const [renameFailed, setRenameFailed] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  usePhoneTabsOnClose(renameOpen);
  usePhoneTabsOnClose(deleteOpen);
  const [deleting, setDeleting] = useState({
    id: "",
    name: "",
    current: false,
  });
  const collapsed = { opacity: 0, height: 0 };
  const rowTransition = reducedMotion
    ? { duration: 0 }
    : { duration: 0.3, ease: [0.22, 0.8, 0.2, 1] as const };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (onSaveAs(name)) setName("");
  };
  return (
    <>
      <div className="profile-list">
        <AnimatePresence initial={false}>
          {Object.entries(profiles).map(([id, profile]) => (
            <motion.div
              className="profile-item"
              key={id}
              initial={collapsed}
              animate={{ opacity: 1, height: "auto" }}
              exit={collapsed}
              transition={rowTransition}
            >
              <div
                className={`profile-row${id === currentProfileId ? " current" : ""}`}
              >
                <button
                  className="profile-select"
                  type="button"
                  aria-pressed={id === currentProfileId}
                  onClick={() => onSwitch(id)}
                >
                  <span className="profile-row-name">{profile.name}</span>
                  <span className="profile-meta">
                    {t("{selected} selected · {completed} completed", {
                      selected: profile.state.selectedCourseIds.length,
                      completed: profile.state.completedCourseIds.length,
                    })}
                  </span>
                </button>
                <button
                  className="profile-icon"
                  type="button"
                  aria-label={t("Rename {name}", { name: profile.name })}
                  onClick={() => {
                    setRenaming(id);
                    setRenameName(profile.name);
                    setRenameFailed(false);
                    setRenameOpen(true);
                  }}
                >
                  ✎
                </button>
                {Object.keys(profiles).length > 1 && (
                  <button
                    className="profile-icon delete"
                    type="button"
                    aria-label={t("Delete {name}", { name: profile.name })}
                    onClick={() => {
                      setDeleting({
                        id,
                        name: profile.name,
                        current: id === currentProfileId,
                      });
                      setDeleteOpen(true);
                    }}
                  >
                    {TRASH}
                  </button>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
      <form className="profile-save" onSubmit={submit}>
        <label htmlFor="profile-name">{t("New profile")}</label>
        <div>
          <input
            id="profile-name"
            placeholder={t("Name")}
            value={name}
            autoComplete="off"
            onChange={(event) => setName(event.target.value)}
          />
          <button type="submit" disabled={!name.trim()}>
            {t("Save")}
          </button>
        </div>
      </form>
      <AnimatePresence initial={false}>
        {error && (
          <ProfileNotice key="profile-save-error">
            <ErrorNotice error={error} language={language} />
          </ProfileNotice>
        )}
      </AnimatePresence>
      <ProfileTransfer store={store} />
      <Dialog.Root open={renameOpen} onOpenChange={setRenameOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-scrim" />
          <Dialog.Content
            className="dialog-panel dialog-panel-compact profile-dialog"
            aria-describedby={undefined}
          >
            <Dialog.Title>{t("Rename profile")}</Dialog.Title>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                if (onRename(renaming, renameName)) setRenameOpen(false);
                else setRenameFailed(true);
              }}
            >
              <input
                className="profile-rename-input"
                aria-label={t("Profile name")}
                value={renameName}
                autoComplete="off"
                autoFocus
                onFocus={(event) => event.target.select()}
                onChange={(event) => setRenameName(event.target.value)}
              />
              <AnimatePresence initial={false}>
                {renameFailed && renameError && (
                  <ProfileNotice key="profile-rename-error">
                    <ErrorNotice error={renameError} language={language} />
                  </ProfileNotice>
                )}
              </AnimatePresence>
              <div className="dialog-foot dialog-foot-wrap">
                <Dialog.Close asChild>
                  <button className="dialog-cancel" type="button">
                    {t("Cancel")}
                  </button>
                </Dialog.Close>
                <button className="dialog-confirm" type="submit">
                  {t("Save")}
                </button>
              </div>
            </form>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <Dialog.Root open={deleteOpen} onOpenChange={setDeleteOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-scrim" />
          <Dialog.Content
            className="dialog-panel dialog-panel-compact"
            aria-describedby={undefined}
          >
            <Dialog.Title>
              {t("Delete profile “{name}”?", { name: deleting.name })}
            </Dialog.Title>
            {deleting.current && (
              <p>
                {t(
                  "This is your current profile. The first remaining profile will be selected instead.",
                )}
              </p>
            )}
            <div className="dialog-foot">
              <Dialog.Close asChild>
                <button className="dialog-cancel" type="button">
                  {t("Cancel")}
                </button>
              </Dialog.Close>
              <button
                className="dialog-confirm"
                type="button"
                onClick={() => {
                  onDelete(deleting.id);
                  setDeleteOpen(false);
                }}
              >
                {t("Delete")}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
