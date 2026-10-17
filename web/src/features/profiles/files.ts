/** One JSON download for the typed browser files the profile menu exports. */
import type { BrowserFile } from "../../state/types";

const PROFILE_FILE_PREFIX = "course-explorer-profile-";
const STATE_FILE_NAME = "course-explorer-saved-data.json";
// Characters that a path segment cannot hold, plus the control range.
const INVALID_FILE_NAME_CHARACTERS = /[<>:"/\\|?*\u0000-\u001f]/g;

function fileName(file: BrowserFile): string {
  if (file.type !== "tuni-course-explorer/profile/2") return STATE_FILE_NAME;
  const name = file.profile.name.replace(INVALID_FILE_NAME_CHARACTERS, "_");
  return `${PROFILE_FILE_PREFIX}${name}.json`;
}

/** Download the typed browser file under the name its kind and profile name supply. */
export function downloadBrowserFile(file: BrowserFile): void {
  const blob = new Blob([JSON.stringify(file, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName(file);
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  // The download reads the blob after the click returns, so the URL is released on the
  // next task.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
