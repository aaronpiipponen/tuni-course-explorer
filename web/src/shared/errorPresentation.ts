/**
 * One error-presentation boundary that maps finite known app-authored failures to the shared
 * wording resource and passes any unstructured message through as explicit diagnostic
 * detail.
 */
import { ApiError } from "../api/http";
import type { DisplayLanguage } from "../state/types";
import { uiText, type UiTextKey } from "./wording";

const KNOWN_MESSAGES: Record<string, UiTextKey> = {
  "Current browser profile is unavailable":
    "Current browser profile is unavailable",
  "Browser profile is unavailable": "Browser profile is unavailable",
  "Profile name cannot be empty": "Profile name cannot be empty",
  "A profile with that name already exists":
    "A profile with that name already exists",
  "The last browser profile cannot be deleted":
    "The last browser profile cannot be deleted",
  "Browser store provider is missing": "Browser store provider is missing",
  "Search session provider is missing": "Search session provider is missing",
  "Saved browser state is invalid": "Saved browser state is invalid",
  "Unsupported saved browser state schema":
    "Unsupported saved browser state schema",
  "Saved browser state has no current profile":
    "Saved browser state has no current profile",
  "Saved browser profile is invalid": "Saved browser profile is invalid",
  "Saved browser profile state is invalid":
    "Saved browser profile state is invalid",
  "Saved browser profile slice search is invalid":
    "Saved browser profile slice search is invalid",
  "Saved browser profile slice compare is invalid":
    "Saved browser profile slice compare is invalid",
  "Saved browser profile slice prerequisites is invalid":
    "Saved browser profile slice prerequisites is invalid",
  "Saved browser profile slice discover is invalid":
    "Saved browser profile slice discover is invalid",
  "Saved browser profile slice structure is invalid":
    "Saved browser profile slice structure is invalid",
  "A module cannot be added inside itself":
    "A module cannot be added inside itself",
  "Structure programmes changed while adding a module":
    "Structure programmes changed while adding a module",
  "Structure moves changed while confirming a module":
    "Structure moves changed while confirming a module",
  "Structure target is unavailable": "Structure target is unavailable",
  "Programme is unavailable": "Programme is unavailable",
  "Programme is already added": "Programme is already added",
  "Unsupported structure rule type": "Unsupported structure rule type",
  "Structure rule entry is missing its source origin":
    "Structure rule entry is missing its source origin",
  "Missing placed course summary": "Missing placed course summary",
  "Missing placed module report": "Missing placed module report",
  "Placed module is missing from the resolved structure":
    "Placed module is missing from the resolved structure",
  "Requested course summary is missing": "Requested course summary is missing",
  "Invalid import file": "Invalid import file",
  "Unsupported file type": "Unsupported file type",
  "Choose one file": "Choose one file",
  "There is no saved data to export": "There is no saved data to export",
  "Invalid Sisu plan file": "Invalid Sisu plan file",
  "Sisu choice is ambiguous": "Sisu choice is ambiguous",
  "Could not copy Sisu import script": "Could not copy Sisu import script",
};

export function errorPresentation(
  error: Error,
  language: DisplayLanguage,
): { summary: string; detail: string | null } {
  if (error instanceof ApiError) {
    if (error.status === 422) {
      return {
        summary: uiText(language, "Invalid request"),
        detail: error.message === "Invalid request" ? null : error.message,
      };
    }
    const generated = `Request failed (${error.status})`;
    return {
      summary: uiText(language, "Request failed ({status})", {
        status: error.status,
      }),
      detail: error.message === generated ? null : error.message,
    };
  }
  const key = KNOWN_MESSAGES[error.message];
  if (key) return { summary: uiText(language, key), detail: null };
  return {
    summary: uiText(language, "Operation failed"),
    detail: error.message,
  };
}
