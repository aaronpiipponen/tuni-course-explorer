/** One accessible shared course-action menu and replacement-dialog owner. */
import { useEffect, useRef, useState, type ReactElement } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import type { CourseSummary } from "../../api/types";
import { addToComparison } from "../../features/compare/actions";
import { ComparisonReplaceDialog } from "../../features/compare/ComparisonReplaceDialog";
import { openPrerequisites } from "../../app/actions";
import { toggleCompleted } from "../../state/course-actions";
import { useFreeChoiceAdd } from "../../features/structure/useFreeChoiceAdd";
import { useProfileSelector } from "../../state/useProfileSelector";
import { ErrorNotice } from "../ErrorNotice";
import { useAction } from "../useAction";
import { useWording } from "../useWording";

export function CourseMenu({
  course,
  children,
  open,
  onOpenChange,
  onInteractionChange,
}: {
  course: CourseSummary;
  children: ReactElement;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInteractionChange?: (active: boolean) => void;
}) {
  const { store, value: inComparison } = useProfileSelector((state) =>
    state.compare.slots.includes(course.group_id),
  );
  const { value: completed } = useProfileSelector((state) =>
    state.completedCourseIds.includes(course.group_id),
  );
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  const [replaceOpen, setReplaceOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const freeChoice = useFreeChoiceAdd(() => triggerRef.current?.focus());
  const onInteractionChangeRef = useRef(onInteractionChange);
  onInteractionChangeRef.current = onInteractionChange;
  useEffect(
    () =>
      onInteractionChangeRef.current?.(
        open || replaceOpen || freeChoice.promptOpen,
      ),
    [open, replaceOpen, freeChoice.promptOpen],
  );
  const addComparison = () =>
    runAction(() => {
      if (addToComparison(store, course.group_id) === "replace-required") {
        onOpenChange(false);
        setReplaceOpen(true);
      } else onOpenChange(false);
    });
  return (
    <>
      <DropdownMenu.Root modal={false} open={open} onOpenChange={onOpenChange}>
        <DropdownMenu.Trigger ref={triggerRef} asChild>
          {children}
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            className="course-menu"
            side="bottom"
            align="center"
            sideOffset={3}
            onCloseAutoFocus={(event) => {
              if (replaceOpen) event.preventDefault();
            }}
          >
            <DropdownMenu.Item
              disabled={inComparison}
              onSelect={(event) => {
                event.preventDefault();
                if (!inComparison) addComparison();
              }}
            >
              {t(inComparison ? "Already in comparison" : "Add to comparison")}
              <span aria-hidden="true">⇄</span>
            </DropdownMenu.Item>
            <DropdownMenu.Item
              onSelect={() => {
                runAction(() => openPrerequisites(store, course.group_id));
                onOpenChange(false);
              }}
            >
              {t("Open prerequisite graph")}
              <span aria-hidden="true">→</span>
            </DropdownMenu.Item>
            <DropdownMenu.Separator />
            <DropdownMenu.Item
              onSelect={() => {
                runAction(() => freeChoice.add([course.group_id]));
                onOpenChange(false);
              }}
            >
              {t("Add to Unplaced studies")}
              <span aria-hidden="true">{t("structure")}</span>
            </DropdownMenu.Item>
            <DropdownMenu.Item
              onSelect={() => {
                runAction(() => toggleCompleted(store, course.group_id));
                onOpenChange(false);
              }}
            >
              {t(completed ? "Mark not completed" : "Mark completed")}
              <span aria-hidden="true">✓</span>
            </DropdownMenu.Item>
            <DropdownMenu.Separator />
            <DropdownMenu.Item asChild>
              <a
                href={course.official_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("Open in Sisu")}
                <span aria-hidden="true">↗</span>
              </a>
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      {error && <ErrorNotice error={error} language={language} />}
      <ComparisonReplaceDialog
        course={course}
        open={replaceOpen}
        onClose={() => {
          setReplaceOpen(false);
          onOpenChange(false);
        }}
        returnFocus={() => triggerRef.current?.focus()}
      />
      {freeChoice.prompt}
    </>
  );
}
