/** Animated root-course picker overlay sharing Compare's substring lookup path. */
import { useProfileSelector } from "../../state/useProfileSelector";
import { useAction } from "../../shared/useAction";
import { CourseLookupBox } from "../../shared/course/CourseLookupBox";
import { PickerOverlay } from "../../shared/PickerOverlay";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { useWording } from "../../shared/useWording";
import {
  setPrerequisitesActiveOnly,
  setPrerequisitesQuery,
  setPrerequisitesRoot,
} from "./actions";

export function RootBox({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { store, value: query } = useProfileSelector(
    (state) => state.prerequisites.courseQuery,
  );
  const { store: activityStore, value: activeOnly } = useProfileSelector(
    (state) => state.prerequisites.activeOnly,
  );
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  return (
    <PickerOverlay
      open={open}
      onClose={onClose}
      eyebrow={`// ${t("choose course")}`}
    >
      {error && <ErrorNotice error={error} language={language} />}
      <CourseLookupBox
        open={open}
        query={query}
        onQuery={(value) => setPrerequisitesQuery(store, value)}
        activeOnly={activeOnly}
        onActiveOnly={(value) =>
          setPrerequisitesActiveOnly(activityStore, value)
        }
        pick={(course) => ({
          text: t("open →"),
          ariaLabel: t("Open prerequisite graph for {code}", {
            code: course.code,
          }),
          onPick: () => {
            runAction(() => setPrerequisitesRoot(store, course.group_id));
            onClose();
          },
        })}
      />
    </PickerOverlay>
  );
}
