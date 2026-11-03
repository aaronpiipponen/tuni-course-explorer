/** Interface wording keys for every Sisu import omission and waiting reason. */
import type { UiTextKey } from "../../shared/wording";
import type { SisuImportIssue } from "./sisu";

/** The one reason-key table shared by the confirmation and the placement notice. */
export const SISU_IMPORT_REASON_KEYS: Record<
  SisuImportIssue["reason"],
  UiTextKey
> = {
  unresolved:
    "Sisu data did not identify this item uniquely, so it was left out.",
  module_not_placed:
    "The catalogue has no structure for this module, so it was left out. Its courses that are in the catalogue are in Unplaced studies.",
  course_not_represented:
    "This course is not in the catalogue, so it was left out together with its completion.",
  no_official_match: "No official match was found, so this item was left out.",
  ambiguous_official_match:
    "Several official items match, so this item was left out.",
  version_choice_pending:
    "This module is matched by name after you choose the version of the module above it.",
};
