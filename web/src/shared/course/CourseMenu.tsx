/** One accessible shared course-action menu and its replacement, move and completion dialogs. */
import { useEffect, useRef, useState, type ReactElement } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import type { CourseSummary } from "../../api/types";
import { addToComparison } from "../../features/compare/actions";
import { ComparisonReplaceDialog } from "../../features/compare/ComparisonReplaceDialog";
import { openComparison, openPrerequisites } from "../../app/actions";
import { CompletedCourseDeselectDialog } from "../../features/structure/CompletedCourseDeselectDialog";
import { revealUnplacedStudies } from "../../features/structure/reveal";
import { useWebFeatures } from "../../app/useWebFeatures";
import {
  placeCourseInUnplaced,
  removeCourseFromSelection,
} from "../../state/course-actions";
import { useProfileSelector } from "../../state/useProfileSelector";
import { ConfirmDialog } from "../ConfirmDialog";
import { ErrorNotice } from "../ErrorNotice";
import type { NoticeLink } from "../noticeContext";
import { useAction } from "../useAction";
import { useNotice } from "../useNotice";
import { uiText } from "../wording";
import { useWording } from "../useWording";
import { courseCredits, courseName } from "./presentation";
import { useCourseCompletion } from "./useCourseCompletion";

/** Render one course action menu and its replacement, move and completion dialogs. */
export function CourseMenu({
  course,
  children,
  open,
  onOpenChange,
  onInteractionChange,
  structureSurface = false,
}: {
  course: CourseSummary;
  children: ReactElement;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInteractionChange?: (active: boolean) => void;
  /** Whether the card is drawn inside Structure of studies, where a move needs no prompt. */
  structureSurface?: boolean;
}) {
  const { embeddings_enabled } = useWebFeatures();
  const { store, value: inComparison } = useProfileSelector((state) =>
    state.compare.slots.includes(course.group_id),
  );
  const { value: completed } = useProfileSelector((state) =>
    state.completedCourseIds.includes(course.group_id),
  );
  const { value: selected } = useProfileSelector((state) =>
    state.selectedCourseIds.includes(course.group_id),
  );
  const { value: placed } = useProfileSelector((state) =>
    state.structure.placedCourseIds.includes(course.group_id),
  );
  const { value: holder } = useProfileSelector(
    (state) => state.structure.courseHolders?.[course.group_id] ?? null,
  );
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  const notice = useNotice();
  const unplacedLink: NoticeLink = {
    label: (displayLanguage) =>
      uiText(displayLanguage, "Unplaced studies (notice)"),
    run: revealUnplacedStudies,
  };
  const unplacedRemovalLink: NoticeLink = {
    label: (displayLanguage) =>
      uiText(displayLanguage, "Unplaced studies (removal notice)"),
    run: revealUnplacedStudies,
  };
  const [replaceOpen, setReplaceOpen] = useState(false);
  const [deselect, setDeselect] = useState<"unplaced" | "holder" | null>(null);
  const [moveConfirm, setMoveConfirm] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const pointerClosed = useRef(false);
  const completion = useCourseCompletion(
    course,
    () => triggerRef.current?.focus(),
    "always",
  );
  const onInteractionChangeRef = useRef(onInteractionChange);
  onInteractionChangeRef.current = onInteractionChange;
  useEffect(
    () =>
      onInteractionChangeRef.current?.(
        open ||
          replaceOpen ||
          completion.open ||
          deselect !== null ||
          moveConfirm,
      ),
    [open, replaceOpen, completion.open, deselect, moveConfirm],
  );
  const announceComparisonAdded = () =>
    notice.show(
      (displayLanguage) =>
        uiText(displayLanguage, "Added {code} to comparison", {
          code: course.code,
        }),
      undefined,
      {
        link: {
          label: (displayLanguage) =>
            uiText(displayLanguage, "comparison (notice)"),
          run: openComparison,
        },
      },
    );
  const addComparison = () =>
    runAction(() => {
      const result = addToComparison(store, course.group_id);
      if (result === "replace-required") {
        onOpenChange(false);
        setReplaceOpen(true);
        return;
      }
      onOpenChange(false);
      if (result === "added") announceComparisonAdded();
    });
  const addToUnplaced = () =>
    runAction(() => {
      placeCourseInUnplaced(store, course.group_id);
      onOpenChange(false);
      notice.show(
        (displayLanguage) =>
          uiText(displayLanguage, "Added {code} to Unplaced studies", {
            code: course.code,
          }),
        undefined,
        { link: unplacedLink },
      );
    });
  const moveToUnplaced = () => {
    // The menu closes before the card moves, so the open menu never repositions around a
    // disappearing trigger.
    onOpenChange(false);
    requestAnimationFrame(() =>
      runAction(() => {
        placeCourseInUnplaced(store, course.group_id);
        notice.show(
          (displayLanguage) =>
            uiText(displayLanguage, "Moved {code} to Unplaced studies", {
              code: course.code,
            }),
          undefined,
          { link: unplacedLink },
        );
      }),
    );
  };
  const removeFromUnplaced = () => {
    if (completed) {
      onOpenChange(false);
      setDeselect("unplaced");
      return;
    }
    onOpenChange(false);
    requestAnimationFrame(() =>
      runAction(() => {
        removeCourseFromSelection(store, course.group_id, false);
        notice.show(
          (displayLanguage) =>
            uiText(displayLanguage, "Removed {code} from Unplaced studies", {
              code: course.code,
            }),
          undefined,
          { link: unplacedRemovalLink },
        );
      }),
    );
  };
  const removeFromHolder = () => {
    if (completed) {
      onOpenChange(false);
      setDeselect("holder");
      return;
    }
    onOpenChange(false);
    requestAnimationFrame(() =>
      runAction(() => {
        placeCourseInUnplaced(store, course.group_id);
        announceMovedFromHolder();
      }),
    );
  };
  const holderLabel = holder
    ? ((language === "fi"
        ? (holder.name_fi ?? holder.name_en)
        : (holder.name_en ?? holder.name_fi)) ?? holder.group_id)
    : null;
  const announceRemoveFromHolder = () => {
    notice.show((displayLanguage) =>
      uiText(displayLanguage, "Removed {code} from {name}", {
        code: course.code,
        name: holderLabel ?? "",
      }),
    );
  };
  const announceMovedFromHolder = () => {
    notice.show(
      (displayLanguage) =>
        uiText(
          displayLanguage,
          "Moved {code} from {name} to Unplaced studies",
          {
            code: course.code,
            name: holderLabel ?? "",
          },
        ),
      undefined,
      { link: unplacedLink },
    );
  };
  const chooseMove = () => {
    if (structureSurface) moveToUnplaced();
    else {
      onOpenChange(false);
      setMoveConfirm(true);
    }
  };
  return (
    <>
      <DropdownMenu.Root modal={false} open={open} onOpenChange={onOpenChange}>
        {/* The card click opens the menu, so a scroll gesture that starts on it stays a scroll. */}
        <DropdownMenu.Trigger
          ref={triggerRef}
          asChild
          onPointerDown={(event) => event.preventDefault()}
        >
          {children}
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            className="course-menu"
            side="bottom"
            align="center"
            sideOffset={3}
            updatePositionStrategy="always"
            onPointerDownOutside={() => {
              pointerClosed.current = true;
            }}
            onCloseAutoFocus={(event) => {
              // A menu action can remove the card that owns the trigger, and a focus restore must
              // never scroll the page to a detached or newly placed element. A pointer on another
              // card must also never pull focus back from the menu that same pointer just opened.
              event.preventDefault();
              if (
                pointerClosed.current ||
                replaceOpen ||
                completion.open ||
                deselect !== null ||
                moveConfirm
              ) {
                pointerClosed.current = false;
                return;
              }
              const trigger = triggerRef.current;
              if (trigger?.isConnected) trigger.focus({ preventScroll: true });
            }}
          >
            <DropdownMenu.Label className="course-menu-title">
              <span className="course-menu-facts">
                <span className="course-menu-code">{course.code}</span>
                <span className="course-credit">
                  {courseCredits(course, language)}
                </span>
                <span
                  className={`course-activity ${course.is_active ? "active" : "inactive"}`}
                >
                  <i aria-hidden="true" />
                  {t(course.is_active ? "active" : "inactive")}
                </span>
              </span>
              <span className="course-menu-name">
                {courseName(course, language)}
              </span>
            </DropdownMenu.Label>
            <DropdownMenu.Separator />
            {embeddings_enabled && (
              <DropdownMenu.Item
                disabled={inComparison}
                onSelect={(event) => {
                  event.preventDefault();
                  if (!inComparison) addComparison();
                }}
              >
                {t(
                  inComparison ? "Already in comparison" : "Add to comparison",
                )}
                <span aria-hidden="true">⇄</span>
              </DropdownMenu.Item>
            )}
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
            {!selected ? (
              <DropdownMenu.Item onSelect={addToUnplaced}>
                {t("Add to Unplaced studies")}
                <span aria-hidden="true">{t("structure")}</span>
              </DropdownMenu.Item>
            ) : !placed ? (
              <DropdownMenu.Item onSelect={removeFromUnplaced}>
                {t("Remove from Unplaced studies")}
                <span aria-hidden="true">{t("structure")}</span>
              </DropdownMenu.Item>
            ) : (
              <>
                <DropdownMenu.Item onSelect={chooseMove}>
                  {t("Move to Unplaced studies")}
                  <span aria-hidden="true">{t("structure")}</span>
                </DropdownMenu.Item>
                {holderLabel && (
                  <DropdownMenu.Item onSelect={removeFromHolder}>
                    <span className="course-menu-ellipsis">
                      {t("Remove from {name}", { name: holderLabel })}
                    </span>
                  </DropdownMenu.Item>
                )}
              </>
            )}
            <DropdownMenu.Item
              onSelect={() => {
                completion.toggle();
                onOpenChange(false);
              }}
            >
              {t(completed ? "Remove completion" : "Mark completed")}
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
      {completion.dialog}
      {embeddings_enabled && (
        <ComparisonReplaceDialog
          course={course}
          open={replaceOpen}
          onClose={() => {
            setReplaceOpen(false);
            onOpenChange(false);
          }}
          onReplaced={announceComparisonAdded}
          returnFocus={() => triggerRef.current?.focus()}
        />
      )}
      <CompletedCourseDeselectDialog
        open={deselect !== null}
        courseCode={course.code}
        unplaced={deselect === "unplaced"}
        onCancel={() => setDeselect(null)}
        onKeepLoose={() => {
          runAction(() => {
            placeCourseInUnplaced(store, course.group_id);
            announceMovedFromHolder();
          });
          setDeselect(null);
        }}
        onRemove={() => {
          const target = deselect;
          runAction(() => {
            removeCourseFromSelection(store, course.group_id, true);
            if (target === "unplaced") {
              notice.show(
                (displayLanguage) =>
                  uiText(
                    displayLanguage,
                    "Removed {code} from Unplaced studies",
                    { code: course.code },
                  ),
                undefined,
                { link: unplacedRemovalLink },
              );
            } else {
              announceRemoveFromHolder();
            }
          });
          setDeselect(null);
        }}
        returnFocus={() => triggerRef.current?.focus()}
      />
      <ConfirmDialog
        open={moveConfirm}
        title={t("Move to Unplaced studies?")}
        description={t(
          "{code} is already in your plan. Move it to Unplaced studies?",
          { code: course.code },
        )}
        confirmLabel={t("Move")}
        onCancel={() => setMoveConfirm(false)}
        onConfirm={() => {
          moveToUnplaced();
          setMoveConfirm(false);
        }}
        returnFocus={() => triggerRef.current?.focus()}
      />
    </>
  );
}
