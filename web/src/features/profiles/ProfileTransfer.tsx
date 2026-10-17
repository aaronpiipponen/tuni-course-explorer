/**
 * Profile, whole-state and Sisu-capture transfer inside the profile menu.
 *
 * The picker and the drop area share one read and dispatch on the file's `type`. Every parsed file
 * waits in one pending import until its confirmation creates the profile, replaces the saved
 * envelope or imports the Sisu hierarchy, and the bottom row holds the help drawer, the script
 * copy and the export disclosure.
 */
import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { AnimatePresence } from "framer-motion";
import type { BrowserImport } from "../../state/types";
import { parseBrowserImport, type BrowserStore } from "../../state/store";
import { useCurrentProfile } from "../../state/useCurrentProfile";
import { prepareSisuProfile, type SisuItem } from "../structure/sisu";
import { Disclosure } from "../../shared/Disclosure";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { HelpTip, type HelpSection } from "../../shared/HelpTip";
import { useAction } from "../../shared/useAction";
import { useWording } from "../../shared/useWording";
import { downloadBrowserFile } from "./files";
import { PROFILE_NOTICE_MS, ProfileNotice } from "./ProfileNotice";

/**
 * The complete console script, copied verbatim by the copy control.
 *
 * The script reads the open Sisu plan page, resolves the modules and courses it shows through
 * anonymous Kori lookups, and downloads one capture file. The text is literal and is copied
 * unchanged.
 */
const SISU_SNIPPET = `// Paste this into the browser console on the Sisu "Structure of studies" page with every module
// expanded. It downloads sisu-plan-capture.json: the plan tree markup and the anonymous Kori
// lookups that resolve the shown modules and courses. It reads the open page and makes anonymous
// GET requests to the public Kori API, nothing else.
(async () => {
  // Every module has to be expanded, or the markup does not hold the whole plan.
  if (document.querySelector('plan-module .collapse[aria-expanded="false"]'))
    throw new Error("Expand every module of the plan first.");

  // One anonymous Kori GET. A 404 means Kori has no record for the id, so it counts as no result.
  async function get(path) {
    const response = await fetch("https://sisu.tuni.fi/kori/api/" + path, {
      method: "GET",
      credentials: "omit", // do not send the Sisu login cookies
    });
    if (response.status === 404) return [];
    if (!response.ok) throw new Error("Kori returned HTTP " + response.status + ".");
    return response.json();
  }

  // The education row only wraps its degrees, so no lookup is made for its own identity.
  const own = (module, selector) =>
    [...module.querySelectorAll(selector)].some(
      (found) => found.closest("plan-module") === module,
    );
  const education = [...document.querySelectorAll("plan-module")].find(
    (module) =>
      module.parentElement.closest("plan-module") === null &&
      !own(module, ".graduate") &&
      !own(module, ".title.grouping-module") &&
      !own(module, '[id^="module-info-modal-open-"]'),
  );

  // Resolve every shown module version id to the group id of its Kori module.
  const statusIds = new Set();
  for (const cell of document.querySelectorAll("plan-module .status [id]")) {
    if (cell.closest("plan-module") !== education) statusIds.add(cell.id);
  }
  const modules = {};
  for (const statusId of statusIds) {
    const versionId = statusId.replace(/-statuscell.*$/, "");
    const body = await get("modules?id=" + versionId);
    modules[statusId] = body.map((module) => module.groupId);
  }

  // Resolve every shown course code to the Kori search hits for it.
  const codes = new Set();
  for (const code of document.querySelectorAll("course-unit-box .courseunit-code")) {
    codes.add(code.textContent.trim());
  }
  const courses = {};
  for (const code of codes) {
    const query = new URLSearchParams({
      fullTextQuery: code,
      universityId: "tuni-university-root-id",
      start: "0",
      limit: "50",
    });
    const body = await get("course-unit-search?" + query);
    if (body.truncated) throw new Error("Kori returned a partial result for " + code + ".");
    courses[code] = body.searchResults.map((result) => ({
      code: result.code,
      groupId: result.groupId,
    }));
  }

  // The plan tree markup; the importer reads the hierarchy out of it.
  const markup = [...document.querySelectorAll("plan-module")]
    .filter((module) => module.parentElement.closest("plan-module") === null)
    .map((module) => module.outerHTML)
    .join("");

  const file = { type: "tuni-course-explorer/sisu/1", markup, modules, courses };
  const blob = new Blob([JSON.stringify(file)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "sisu-plan-capture.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 0);
})();`;

function asError(caught: unknown): Error {
  return caught instanceof Error ? caught : new Error(String(caught));
}

/** Return the captured items whose identity is unresolved, in capture order. */
function unresolvedItems(items: readonly SisuItem[]): SisuItem[] {
  return items.flatMap((item) => [
    ...(item.groupId === null ? [item] : []),
    ...(item.kind === "module" ? unresolvedItems(item.children) : []),
  ]);
}

/** Return the code and name that label one captured item in the confirmation and the result notice. */
function itemLabel(item: SisuItem): string {
  return item.code ? `${item.code} ${item.name}` : item.name;
}

export function ProfileTransfer({ store }: { store: BrowserStore }) {
  const { profiles } = useCurrentProfile();
  const { language, t } = useWording();
  const { runAction, error: exportError } = useAction();
  const [exportOpen, setExportOpen] = useState(false);
  const [copyStatus, setCopyStatus] = useState(false);
  const [copyError, setCopyError] = useState<Error | null>(null);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const copyOpener = useRef<HTMLElement | null>(null);
  const copyButton = useRef<HTMLButtonElement>(null);
  const [fileError, setFileError] = useState<Error | null>(null);
  const [confirmError, setConfirmError] = useState<Error | null>(null);
  const [pendingImport, setPendingImport] = useState<BrowserImport | null>(
    null,
  );
  const [sisuName, setSisuName] = useState("");
  const [reading, setReading] = useState(false);
  const importDisabled = reading || pendingImport !== null;

  // A pending notice timer never outlives the panel.
  useEffect(
    () => () => {
      if (copyTimer.current !== null) clearTimeout(copyTimer.current);
    },
    [],
  );

  const acceptFile = async (file: File) => {
    setReading(true);
    setFileError(null);
    try {
      const parsed = parseBrowserImport(await file.text());
      setConfirmError(null);
      setSisuName("");
      setPendingImport(parsed);
    } catch (caught) {
      setFileError(asError(caught));
    } finally {
      setReading(false);
    }
  };

  const pick = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // An emptied value lets the same file be picked again.
    event.target.value = "";
    if (file) void acceptFile(file);
  };

  const drop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    if (importDisabled) return;
    const files = event.dataTransfer.files;
    if (files.length !== 1) {
      setFileError(new Error("Choose one file"));
      return;
    }
    void acceptFile(files[0]);
  };

  /**
   * Copy the literal script through one path that works on a plain HTTP origin: select it in a
   * temporary textarea and copy the selection during the click. The element sits inside the open
   * panel, so the menu does not read its focus as a dismissal, and the element, the focus and the
   * previous selection are restored before the status is reported. A successful copy restarts the
   * notice lifetime.
   */
  const copySnippet = () => {
    copyOpener.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const selection = document.getSelection();
    const previous = selection
      ? Array.from({ length: selection.rangeCount }, (_, index) =>
          selection.getRangeAt(index),
        )
      : [];
    const hold = document.createElement("textarea");
    hold.className = "profile-snippet-hold";
    hold.setAttribute("readonly", "");
    hold.value = SISU_SNIPPET;
    (copyButton.current?.parentElement ?? document.body).append(hold);
    hold.select();
    let copied = false;
    try {
      copied = document.execCommand("copy");
    } catch {
      copied = false;
    }
    hold.remove();
    selection?.removeAllRanges();
    previous.forEach((range) => selection?.addRange(range));
    copyOpener.current?.focus();
    setCopyStatus(copied);
    setCopyError(
      copied ? null : new Error("Could not copy Sisu import script"),
    );
    if (copyTimer.current !== null) clearTimeout(copyTimer.current);
    copyTimer.current = copied
      ? setTimeout(() => setCopyStatus(false), PROFILE_NOTICE_MS)
      : null;
  };

  const confirm = () => {
    if (!pendingImport) return;
    try {
      if (pendingImport.type === "tuni-course-explorer/profile/2")
        store.importProfile(pendingImport.profile);
      else if (pendingImport.type === "tuni-course-explorer/sisu/1")
        store.importProfile(
          prepareSisuProfile(pendingImport, sisuName, language),
        );
      else {
        store.restoreState(pendingImport.state);
        window.location.reload();
        return;
      }
    } catch (caught) {
      setConfirmError(asError(caught));
      return;
    }
    setPendingImport(null);
    setConfirmError(null);
    setSisuName("");
  };

  const pendingProfile =
    pendingImport?.type === "tuni-course-explorer/profile/2"
      ? pendingImport.profile
      : null;
  const pendingSisu =
    pendingImport?.type === "tuni-course-explorer/sisu/1"
      ? pendingImport
      : null;
  const omitted = pendingSisu ? unresolvedItems(pendingSisu.programmes) : [];
  const help: readonly HelpSection[] = [
    {
      heading: t("Export"),
      items: [
        {
          term: t("Export"),
          text: t(
            "Export any listed profile or all saved data as one file. Select an entry to download it.",
          ),
        },
      ],
    },
    {
      heading: t("Import"),
      items: [
        {
          term: t("Import"),
          text: t(
            "Import a profile, all saved data or a Sisu plan from a .json file. A profile becomes a new profile, all saved data replaces everything after you confirm, and a Sisu plan becomes a new profile whose choices are placed when Structure of studies first loads the programmes.",
          ),
        },
      ],
    },
    {
      heading: t("Sisu plan"),
      items: [
        {
          term: t("Import Sisu plan"),
          text: t(
            "Import a Sisu plan: expand every module in Sisu, review the copied script and run it in Sisu's browser console, then import the downloaded sisu-plan-capture.json here under a new profile name. The script reads the open Sisu page and the public Kori interface anonymously. The downloaded file stays in this browser.",
          ),
        },
      ],
    },
  ];

  return (
    <div className="profile-transfer">
      <label
        className="profile-drop"
        onDrop={drop}
        onDragOver={(event) => event.preventDefault()}
      >
        <span className="profile-choose">{t("Choose file")}</span>
        <span className="profile-drop-note">{t("or drop a .json file")}</span>
        <input
          className="profile-file"
          type="file"
          accept=".json,application/json"
          aria-label={t("Import")}
          disabled={importDisabled}
          onChange={pick}
        />
      </label>
      {exportError && <ErrorNotice error={exportError} language={language} />}
      {fileError && <ErrorNotice error={fileError} language={language} />}
      <div className="profile-transfer-actions">
        <HelpTip sections={help} />
        <div className="profile-transfer-controls">
          <button
            className="profile-transfer-toggle"
            type="button"
            ref={copyButton}
            onClick={copySnippet}
          >
            {t("Copy Sisu import script")}
          </button>
          <button
            className="profile-transfer-toggle"
            type="button"
            aria-expanded={exportOpen}
            aria-controls="profile-export-list"
            onClick={() => setExportOpen((open) => !open)}
          >
            {t("Export")}
          </button>
        </div>
      </div>
      <AnimatePresence initial={false}>
        {copyStatus && (
          <ProfileNotice key="profile-copy-status">
            <p className="error-notice profile-copy-notice" role="status">
              {t("Sisu import script copied")}
            </p>
          </ProfileNotice>
        )}
      </AnimatePresence>
      {copyError && <ErrorNotice error={copyError} language={language} />}
      <Disclosure open={exportOpen}>
        <div className="profile-export" id="profile-export-list">
          {Object.entries(profiles).map(([id, profile]) => (
            <button
              className="profile-export-item"
              key={id}
              type="button"
              onClick={() =>
                runAction(() => downloadBrowserFile(store.exportProfile(id)))
              }
            >
              {profile.name}
            </button>
          ))}
          <button
            className="profile-export-item"
            type="button"
            onClick={() =>
              runAction(() => downloadBrowserFile(store.exportState()))
            }
          >
            {t("All saved data")}
          </button>
        </div>
      </Disclosure>
      <Dialog.Root
        open={pendingImport !== null}
        onOpenChange={(open) => {
          if (open) return;
          setPendingImport(null);
          setConfirmError(null);
          setSisuName("");
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-scrim" />
          <Dialog.Content
            className="dialog-panel dialog-panel-compact"
            aria-describedby={undefined}
          >
            {pendingProfile ? (
              <>
                <Dialog.Title>
                  {t("Import profile “{name}”?", {
                    name: pendingProfile.name,
                  })}
                </Dialog.Title>
                <p>
                  {t(
                    "This creates a new profile named “{name}” and makes it current.",
                    { name: pendingProfile.name },
                  )}
                </p>
              </>
            ) : pendingSisu ? (
              <>
                <Dialog.Title>{t("Import Sisu plan")}</Dialog.Title>
                <label htmlFor="sisu-profile-name">{t("Profile name")}</label>
                <input
                  id="sisu-profile-name"
                  className="profile-rename-input"
                  value={sisuName}
                  autoComplete="off"
                  autoFocus
                  onChange={(event) => setSisuName(event.target.value)}
                />
                <p>
                  {t(
                    "This creates a new profile with these programmes: {names}.",
                    {
                      names: pendingSisu.programmes
                        .map((programme) => programme.name)
                        .join(", "),
                    },
                  )}
                </p>
                {omitted.length > 0 && (
                  <>
                    <p>{t("Left out of the import:")}</p>
                    <ul className="sisu-omitted">
                      {omitted.map((item, index) => (
                        <li key={`${item.code ?? ""}:${item.name}:${index}`}>
                          {itemLabel(item)}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </>
            ) : (
              <>
                <Dialog.Title>{t("Replace all saved data?")}</Dialog.Title>
                <p>
                  {t(
                    "This replaces every profile in this browser with the imported saved data.",
                  )}
                </p>
              </>
            )}
            {confirmError && (
              <ErrorNotice error={confirmError} language={language} />
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
                disabled={pendingSisu !== null && sisuName.trim() === ""}
                onClick={confirm}
              >
                {pendingProfile || pendingSisu ? t("Import") : t("Replace")}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
