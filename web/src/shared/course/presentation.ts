/** Official course-name and credit display formatting. */
import type { CourseSummary, DisplayLanguage } from "../../api/types";
import { uiText } from "../wording";

/** Return the name in the requested language, the other language, or the fallback. */
export function localizedName<T>(
  language: DisplayLanguage,
  nameFi: string | null,
  nameEn: string | null,
  fallback: T,
): string | T {
  return (
    (language === "fi" ? nameFi : nameEn) ??
    (language === "fi" ? nameEn : nameFi) ??
    fallback
  );
}

/** Return the display name of one course, falling back to its code. */
export function courseName(
  course: Pick<CourseSummary, "code" | "name_fi" | "name_en">,
  language: DisplayLanguage,
): string {
  return localizedName(language, course.name_fi, course.name_en, course.code);
}

/** Return one course's credit range as display text. */
export function courseCredits(
  course: Pick<CourseSummary, "credits_min" | "credits_max">,
  language: DisplayLanguage,
): string {
  const low = Number(course.credits_min);
  const high = course.credits_max === null ? null : Number(course.credits_max);
  const value = high === null || low === high ? `${low}` : `${low}–${high}`;
  return uiText(language, "{value} cr", { value });
}
