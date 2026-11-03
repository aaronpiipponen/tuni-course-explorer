/**
 * Profile, whole-state and Sisu-capture transfer inside the profile menu.
 *
 * The picker and the drop area share one read and dispatch on the file's `type`. Every parsed file
 * waits in one pending import until its confirmation creates the profile, replaces the saved
 * envelope or imports the Sisu hierarchy, and the bottom row holds the help drawer, the script
 * copy and the export disclosure. The component also renders its import area alone, without that
 * row, for the empty structure tab.
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
import type { BrowserImport, Profile } from "../../state/types";
import { parseBrowserImport, type BrowserStore } from "../../state/store";
import { useCurrentProfile } from "../../state/useCurrentProfile";
import { useReadCache } from "../../app/useReadCache";
import {
  prepareSisuProfile,
  type SisuImportIssue,
  type SisuItem,
  type SisuPlan,
} from "../structure/sisu";
import { itemLabel, SisuIssueItem } from "../structure/SisuImportNotice";
import { matchSisuPdfRows } from "../structure/sisuPdfMatch";
import { Disclosure } from "../../shared/Disclosure";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { HelpLink, HelpTip, type HelpSection } from "../../shared/HelpTip";
import { useAction } from "../../shared/useAction";
import { useWording } from "../../shared/useWording";
import { usePhoneTabsOnClose } from "../../shared/usePhoneTabsOnClose";
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

  // The plan tree markup is read by the importer to recover its hierarchy.
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

/**
 * One PDF plan waiting in this component: the matched plan and its transient issues. It is neither
 * a `BrowserImport` nor a persisted file variant.
 */
type PendingSisuPdf = {
  kind: "sisu-pdf";
  plan: SisuPlan;
  issues: readonly SisuImportIssue[];
};

/**
 * Return the captured items whose identity is unresolved, in capture order.
 *
 * An uncoded module carries no identity of its own, and placement resolves it by official name
 * inside its parent, so its own pre-confirmation issue is left to that placement notice. Its
 * children are still reported.
 */
function unresolvedIssues(items: readonly SisuItem[]): SisuImportIssue[] {
  return items.flatMap((item) => [
    ...(item.groupId === null && !(item.kind === "module" && item.code === null)
      ? [{ name: item.name, code: item.code, reason: "unresolved" as const }]
      : []),
    ...(item.kind === "module" ? unresolvedIssues(item.children) : []),
  ]);
}

/** Render the profile export, import and Sisu capture controls. */
export function ProfileTransfer({
  store,
  importOnly = false,
}: {
  store: BrowserStore;
  /** Render only the import area and its confirmations, without the export and copy controls. */
  importOnly?: boolean;
}) {
  const { profiles } = useCurrentProfile();
  const { language, t } = useWording();
  const cache = useReadCache();
  const { runAction, error: exportError } = useAction();
  const [exportOpen, setExportOpen] = useState(false);
  const [copyStatus, setCopyStatus] = useState(false);
  const [copyError, setCopyError] = useState<Error | null>(null);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const copyOpener = useRef<HTMLElement | null>(null);
  const copyButton = useRef<HTMLButtonElement>(null);
  const [fileError, setFileError] = useState<Error | null>(null);
  const [confirmError, setConfirmError] = useState<Error | null>(null);
  const [pendingImport, setPendingImport] = useState<
    BrowserImport | PendingSisuPdf | null
  >(null);
  const [sisuName, setSisuName] = useState("");
  const [reading, setReading] = useState(false);
  const operation = useRef<AbortController | null>(null);
  usePhoneTabsOnClose(pendingImport !== null);
  const importDisabled = reading || pendingImport !== null;

  // A pending notice timer and a running file read never outlive the panel.
  useEffect(() => {
    return () => {
      operation.current?.abort();
      if (copyTimer.current !== null) clearTimeout(copyTimer.current);
    };
  }, []);

  const acceptFile = async (file: File) => {
    const controller = new AbortController();
    operation.current = controller;
    setReading(true);
    setFileError(null);
    try {
      if (
        file.type === "application/pdf" ||
        file.name.toLowerCase().endsWith(".pdf")
      ) {
        const { readSisuPdf } = await import("../structure/sisuPdf");
        const rows = await readSisuPdf(file, controller.signal);
        if (controller.signal.aborted) return;
        const matched = await matchSisuPdfRows(rows, cache, controller.signal);
        if (controller.signal.aborted) return;
        setConfirmError(null);
        setSisuName("");
        setPendingImport({ kind: "sisu-pdf", ...matched });
        return;
      }
      const parsed = parseBrowserImport(await file.text());
      if (controller.signal.aborted) return;
      setConfirmError(null);
      setSisuName("");
      setPendingImport(parsed);
    } catch (caught) {
      if (controller.signal.aborted) return;
      setFileError(asError(caught));
    } finally {
      operation.current = null;
      if (!controller.signal.aborted) setReading(false);
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
      let target: Profile;
      if ("kind" in pendingImport) {
        target = prepareSisuProfile(pendingImport.plan, sisuName, language);
      } else if (pendingImport.type === "tuni-course-explorer/profile/3") {
        target = pendingImport.profile;
      } else if (pendingImport.type === "tuni-course-explorer/sisu/1") {
        target = prepareSisuProfile(pendingImport, sisuName, language);
      } else {
        store.restoreState(pendingImport.state);
        window.location.reload();
        return;
      }
      if (overwrite && existingProfileId !== null)
        store.overwriteProfile(existingProfileId, target.state);
      else store.importProfile(target);
    } catch (caught) {
      setConfirmError(asError(caught));
      return;
    }
    setPendingImport(null);
    setConfirmError(null);
    setSisuName("");
  };

  const pendingProfile =
    pendingImport !== null &&
    "type" in pendingImport &&
    pendingImport.type === "tuni-course-explorer/profile/3"
      ? pendingImport.profile
      : null;
  const pendingPdf =
    pendingImport !== null && "kind" in pendingImport ? pendingImport : null;
  const pendingCapture =
    pendingImport !== null &&
    "type" in pendingImport &&
    pendingImport.type === "tuni-course-explorer/sisu/1"
      ? pendingImport
      : null;
  const pendingSisu = pendingPdf
    ? { plan: pendingPdf.plan, issues: pendingPdf.issues }
    : pendingCapture
      ? {
          plan: pendingCapture as SisuPlan,
          issues: unresolvedIssues(pendingCapture.programmes),
        }
      : null;
  const pendingName = pendingProfile
    ? pendingProfile.name.trim()
    : pendingSisu
      ? sisuName.trim()
      : "";
  const existingProfileId = pendingName
    ? (Object.entries(profiles).find(
        ([, profile]) => profile.name === pendingName,
      )?.[0] ?? null)
    : null;
  const overwrite =
    existingProfileId !== null &&
    (pendingProfile !== null || pendingSisu !== null);
  const waiting =
    pendingSisu?.issues.filter(
      (issue) => issue.reason === "version_choice_pending",
    ) ?? [];
  const omitted =
    pendingSisu?.issues.filter(
      (issue) => issue.reason !== "version_choice_pending",
    ) ?? [];
  const importHelp: readonly HelpSection[] = [
    {
      heading: t("Import"),
      items: [
        {
          term: (
            <HelpLink href="/docs#guide-profiles/importing-a-file">
              {t("Import")}
            </HelpLink>
          ),
          text: t(
            "Choose or drop one .json or .pdf file. A profile file creates a separate profile after confirmation, or overwrites the profile that already has its name. All saved data replaces every profile in this browser after confirmation. A Sisu capture or a supported Sisu plan PDF asks for a profile name, then places its choices and completions when Structure of studies loads its programmes. Cancel leaves saved data unchanged.",
          ),
        },
        {
          term: (
            <HelpLink href="/docs#guide-sisu-import/printing-the-plan">
              {t("Sisu plan")}
            </HelpLink>
          ),
          text: t(
            "A supported Sisu plan PDF imports the same way. In Sisu, open Structure of studies, choose ⋯ beside New study plan, choose Print study plan and save as PDF. The PDF is read in this browser. Official catalogue and structure reads use this site. Omitted items and their candidates are listed for you to check. Some modules may ask you to choose a version. The PDF contains personal identity data, so do not share it casually.",
          ),
        },
      ],
    },
    {
      heading: t("Sisu plan"),
      items: [
        {
          term: (
            <HelpLink href="/docs#guide-sisu-import/capturing-the-plan">
              {t("Import Sisu plan")}
            </HelpLink>
          ),
          text: (
            <>
              {t(
                "Open your plan in Sisu's Structure of studies and expand every module. Copy Sisu import script copies a browser-console script. Read the",
              )}{" "}
              <HelpLink href="/docs#guide-sisu-import/the-script">
                {t("whole script")}
              </HelpLink>{" "}
              {t(
                "before running it in that Sisu tab. It reads the open page and makes anonymous requests to the public Kori interface without Sisu login cookies. Import the downloaded sisu-plan-capture.json here and name the new profile. The file is read in this browser, not uploaded. Check the import's notices for items it could not place.",
              )}
            </>
          ),
        },
      ],
    },
  ];
  const help: readonly HelpSection[] = importOnly
    ? importHelp
    : [
        {
          heading: t("Profiles"),
          items: [
            {
              term: (
                <HelpLink href="/docs#guide-profiles/the-profile-control">
                  {t("Profiles")}
                </HelpLink>
              ),
              text: t(
                "A profile holds your language, selected and completed courses, and tab settings in this browser. A new profile starts as a copy of the open profile. Switching profiles leaves the open tab in place. Export a file to move your plan to another browser or device.",
              ),
            },
          ],
        },
        {
          heading: t("Export"),
          items: [
            {
              term: (
                <HelpLink href="/docs#guide-profiles/exporting-a-profile-or-the-saved-data">
                  {t("Export")}
                </HelpLink>
              ),
              text: t(
                "Open Export and select a profile to download it as a .json file. All saved data downloads every profile and setting together. Exporting changes no profile.",
              ),
            },
          ],
        },
        ...importHelp,
      ];

  return (
    <div className="profile-transfer">
      {importOnly && (
        <h3 className="profile-transfer-heading">{t("Import")}</h3>
      )}
      <label
        className="profile-drop"
        onDrop={drop}
        onDragOver={(event) => event.preventDefault()}
      >
        <span className="profile-drop-text">
          <span className="profile-choose">
            {t(importOnly ? "Choose" : "Choose file")}
          </span>{" "}
          <span className="profile-drop-note">
            {t(
              importOnly
                ? "or drop a PDF print of your Sisu study plan or a JSON profile export"
                : "or drop a .json or .pdf file",
            )}
          </span>
        </span>
        <input
          className="profile-file"
          type="file"
          accept=".json,application/json,.pdf,application/pdf"
          aria-label={t("Import")}
          disabled={importDisabled}
          onChange={pick}
        />
      </label>
      {!importOnly && exportError && (
        <ErrorNotice error={exportError} language={language} />
      )}
      {fileError && <ErrorNotice error={fileError} language={language} />}
      {importOnly ? (
        <div className="profile-transfer-actions profile-transfer-actions-import">
          <button
            className="profile-transfer-toggle"
            type="button"
            ref={copyButton}
            onClick={copySnippet}
          >
            {t("Copy Sisu import script")}
          </button>
          <HelpTip
            title={t("Import")}
            explain="Explain import"
            sections={help}
          />
        </div>
      ) : (
        <div className="profile-transfer-actions">
          <HelpTip
            title={t("Profiles")}
            explain="Explain profiles and import"
            sections={help}
          />
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
      )}
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
      {!importOnly && (
        <Disclosure open={exportOpen}>
          <div className="profile-export" id="profile-export-list">
            <p className="profile-export-hint">
              {t("Select which file to export")}
            </p>
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
      )}
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
                  {overwrite
                    ? t(
                        "This replaces the saved data of the profile “{name}” and makes it current.",
                        { name: pendingProfile.name },
                      )
                    : t(
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
                  {overwrite
                    ? t(
                        "This replaces the saved data of the profile “{name}” with these programmes: {names}.",
                        {
                          name: pendingName,
                          names: pendingSisu.plan.programmes
                            .map((programme) => programme.name)
                            .join(", "),
                        },
                      )
                    : t(
                        "This creates a new profile with these programmes: {names}.",
                        {
                          names: pendingSisu.plan.programmes
                            .map((programme) => programme.name)
                            .join(", "),
                        },
                      )}
                </p>
                {waiting.length > 0 && (
                  <ul className="sisu-omitted">
                    {waiting.map((issue, index) => (
                      <li
                        key={`waiting:${issue.code ?? ""}:${issue.name}:${index}`}
                      >
                        <SisuIssueItem
                          label={itemLabel(issue)}
                          reason={issue.reason}
                        />
                      </li>
                    ))}
                  </ul>
                )}
                {omitted.length > 0 && (
                  <>
                    <p>{t("Left out of the import:")}</p>
                    <ul className="sisu-omitted">
                      {omitted.map((issue, index) => (
                        <li key={`${issue.code ?? ""}:${issue.name}:${index}`}>
                          <SisuIssueItem
                            label={itemLabel(issue)}
                            reason={issue.reason}
                          >
                            {issue.candidates &&
                              issue.candidates.length > 0 && (
                                <div>
                                  <p>{t("Matching official items:")}</p>
                                  <ul>
                                    {issue.candidates.map((candidate) => (
                                      <li key={candidate.groupId}>
                                        {candidate.code
                                          ? `${candidate.code} `
                                          : ""}
                                        {candidate.name} ({candidate.groupId})
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                          </SisuIssueItem>
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
            <AnimatePresence initial={false}>
              {overwrite && (
                <ProfileNotice key="profile-existing-name">
                  <ErrorNotice
                    error={new Error("A profile with that name already exists")}
                    language={language}
                  />
                </ProfileNotice>
              )}
              {confirmError && (
                <ProfileNotice key="profile-confirm-error">
                  <ErrorNotice error={confirmError} language={language} />
                </ProfileNotice>
              )}
            </AnimatePresence>
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
                {overwrite
                  ? t("Overwrite")
                  : pendingProfile || pendingSisu
                    ? t("Import")
                    : t("Replace")}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
