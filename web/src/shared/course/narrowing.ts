/**
 * Local official narrowing over the one cached minimal catalogue.
 *
 * The matching and ordering follow the server-owned official substring contract: the displayed
 * official name wins with the other official name as fallback, code containment never needs a
 * name, and the sort is active first, named before unnamed, normalized name, normalized code and
 * canonical ID. Module rows take the programme-first order ahead of that key, and one row carries a
 * whole canonical group with every eligible candidate. Strings compare by Unicode code point, and
 * no locale collation applies.
 */
import type {
  CatalogueCourse,
  CatalogueReport,
  DisplayLanguage,
  ModuleLookupGroup,
} from "../../api/types";
import { normalizeLookup } from "./unicode";

type DisplayedName = string | null;

function officialDisplayName(
  values: { name_fi: string | null; name_en: string | null },
  language: DisplayLanguage,
): DisplayedName {
  return language === "fi"
    ? (values.name_fi ?? values.name_en)
    : (values.name_en ?? values.name_fi);
}

function matches(
  normalizedQuery: string,
  name: DisplayedName,
  code: string | null,
) {
  if (code !== null && normalizeLookup(code).includes(normalizedQuery))
    return true;
  return name !== null && normalizeLookup(name).includes(normalizedQuery);
}

/** Compare two strings by Unicode code point, preserving Python lexical ordering. */
export function compareCodePoints(left: string, right: string): number {
  const leftPoints = Array.from(left, (character) => character.codePointAt(0)!);
  const rightPoints = Array.from(right, (character) =>
    character.codePointAt(0)!,
  );
  const length = Math.min(leftPoints.length, rightPoints.length);
  for (let index = 0; index < length; index++) {
    if (leftPoints[index] !== rightPoints[index])
      return leftPoints[index] < rightPoints[index] ? -1 : 1;
  }
  return leftPoints.length - rightPoints.length;
}

type SortKey = {
  unnamed: boolean;
  name: string;
  code: string;
  id: string;
};

function nameCodeKey(
  groupId: string,
  name: DisplayedName,
  code: string | null,
): SortKey {
  return {
    unnamed: name === null,
    name: name === null ? "" : normalizeLookup(name),
    code: normalizeLookup(code ?? ""),
    id: groupId,
  };
}

function compareKeys(left: SortKey, right: SortKey): number {
  if (left.unnamed !== right.unnamed) return left.unnamed ? 1 : -1;
  for (const field of ["name", "code", "id"] as const) {
    const order = compareCodePoints(left[field], right[field]);
    if (order !== 0) return order;
  }
  return 0;
}

/**
 * Return every official course whose displayed name or code contains the query.
 *
 * An empty normalized query returns no rows. With `activeOnly` only active courses are returned.
 */
export function narrowCourses(
  courses: readonly CatalogueCourse[],
  query: string,
  language: DisplayLanguage,
  activeOnly: boolean,
): readonly CatalogueCourse[] {
  const normalizedQuery = normalizeLookup(query);
  if (!normalizedQuery) return [];
  const matchesQuery = courses.filter((course) => {
    if (activeOnly && !course.is_active) return false;
    return matches(
      normalizedQuery,
      officialDisplayName(course, language),
      course.code,
    );
  });
  return [...matchesQuery].sort((left, right) => {
    if (left.is_active !== right.is_active) return left.is_active ? -1 : 1;
    return compareKeys(
      nameCodeKey(
        left.group_id,
        officialDisplayName(left, language),
        left.code,
      ),
      nameCodeKey(
        right.group_id,
        officialDisplayName(right, language),
        right.code,
      ),
    );
  });
}

/**
 * Return one row per canonical module group that any eligible candidate matches.
 *
 * An empty normalized query returns no rows. A group row carries the displayed candidate's
 * official kind, code and names and every eligible candidate of the group, so a query that matches
 * one sibling shows the whole group without choosing a version. Programmes precede other modules,
 * then the displayed name and code decide the order and the canonical group identity breaks an
 * otherwise equal tie. Several matching candidates of one group take the displayed-name and code
 * order with the exact version identity as the tie-break, and the first of them supplies the row's
 * display fields. Modules have no activity filter.
 */
export function narrowModules(
  modules: CatalogueReport["modules"],
  query: string,
  language: DisplayLanguage,
): readonly ModuleLookupGroup[] {
  const normalizedQuery = normalizeLookup(query);
  if (!normalizedQuery) return [];
  const rows: { group: ModuleLookupGroup; name: DisplayedName }[] = [];
  for (const module of modules) {
    const matching = module.candidates
      .filter((candidate) =>
        matches(
          normalizedQuery,
          officialDisplayName(candidate, language),
          candidate.code,
        ),
      )
      .sort((left, right) => {
        const order = compareKeys(
          nameCodeKey(
            module.group_id,
            officialDisplayName(left, language),
            left.code,
          ),
          nameCodeKey(
            module.group_id,
            officialDisplayName(right, language),
            right.code,
          ),
        );
        if (order !== 0) return order;
        return compareCodePoints(left.sisu_module_id, right.sisu_module_id);
      });
    if (matching.length === 0) continue;
    const display = matching[0];
    rows.push({
      group: {
        group_id: module.group_id,
        module_type: display.module_type,
        code: display.code,
        name_fi: display.name_fi,
        name_en: display.name_en,
        candidates: module.candidates,
      },
      name: officialDisplayName(display, language),
    });
  }
  return rows
    .sort((left, right) => {
      const leftProgramme = left.group.module_type === "DegreeProgramme";
      const rightProgramme = right.group.module_type === "DegreeProgramme";
      if (leftProgramme !== rightProgramme) return leftProgramme ? -1 : 1;
      return compareKeys(
        nameCodeKey(left.group.group_id, left.name, left.group.code),
        nameCodeKey(right.group.group_id, right.name, right.group.code),
      );
    })
    .map((row) => row.group);
}
