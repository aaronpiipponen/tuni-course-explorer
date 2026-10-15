/** Official course-name and credit display formatting. */
import type { CourseSummary, DisplayLanguage } from "../../api/types";
import { uiText } from "../wording";

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

export function courseName(
  course: CourseSummary,
  language: DisplayLanguage,
): string {
  return localizedName(language, course.name_fi, course.name_en, course.code);
}

export function courseCredits(
  course: CourseSummary,
  language: DisplayLanguage,
): string {
  const low = Number(course.credits_min);
  const high = course.credits_max === null ? null : Number(course.credits_max);
  const value = high === null || low === high ? `${low}` : `${low}–${high}`;
  return uiText(language, "{value} cr", { value });
}
