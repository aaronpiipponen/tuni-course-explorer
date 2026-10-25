/** Shared Unplaced studies addition used by every course card and both add-all actions. */
import { useContext } from "react";
import { setActiveTab } from "../../app/sessionTab";
import { StoreContext } from "../../state/context";
import type { DisplayLanguage } from "../../state/types";
import { useNotice } from "../../shared/useNotice";
import { uiText } from "../../shared/wording";
import { addCoursesToFreeChoice } from "../../state/course-actions";

/** Return the shared addition action, which reports the count the latest saved selection gained. */
export function useFreeChoiceAdd(): { add(ids: readonly string[]): void } {
  const store = useContext(StoreContext);
  const notice = useNotice();
  if (!store) throw new Error("Browser store provider is missing");
  const countText = (language: DisplayLanguage, count: number): string =>
    count === 0
      ? uiText(language, "No courses added. Selection unchanged.")
      : count === 1
        ? uiText(language, "Added {count} course to Unplaced studies", {
            count,
          })
        : uiText(language, "Added {count} courses to Unplaced studies", {
            count,
          });
  return {
    add: (ids: readonly string[]) => {
      const count = addCoursesToFreeChoice(store, ids);
      notice.show((language) => countText(language, count), {
        label: (language) => uiText(language, "Structure of studies"),
        run: () => setActiveTab("structure"),
      });
    },
  };
}
