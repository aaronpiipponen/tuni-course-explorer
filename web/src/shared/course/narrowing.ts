/**
 * Local official narrowing over the one cached minimal catalogue.
 *
 * The matching and ordering follow the server-owned official substring contract: the displayed
 * official name wins with the other official name as fallback, code containment never needs a
 * name, and the sort is active first, named before unnamed, normalized name, normalized code and
 * canonical ID. Module rows take the programme-first order ahead of that key, and one row carries a
 * whole canonical group with every eligible candidate. Strings compare by Unicode code point, and
 * no locale collation applies.
 *
 * Normalization and sort keys are built once per catalogue array, so typing a query scans
 * precomputed text and never repeats normalization for every keystroke.
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

/** Compare two strings by Unicode code point, preserving Python lexical ordering. */
export function compareCodePoints(left: string, right: string): number {
  let leftIndex = 0;
  let rightIndex = 0;
  while (leftIndex < left.length && rightIndex < right.length) {
    const leftPoint = left.codePointAt(leftIndex)!;
    const rightPoint = right.codePointAt(rightIndex)!;
    if (leftPoint !== rightPoint) return leftPoint < rightPoint ? -1 : 1;
    leftIndex += leftPoint > 0xffff ? 2 : 1;
    rightIndex += rightPoint > 0xffff ? 2 : 1;
  }
  return Number(leftIndex < left.length) - Number(rightIndex < right.length);
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

type CourseEntry = {
  course: CatalogueCourse;
  active: boolean;
  normalizedCode: string;
  normalizedName: Record<DisplayLanguage, string | null>;
  key: Record<DisplayLanguage, SortKey>;
};

const courseIndexes = new WeakMap<
  readonly CatalogueCourse[],
  readonly CourseEntry[]
>();

function buildCourseEntry(course: CatalogueCourse): CourseEntry {
  const key = (language: DisplayLanguage): SortKey =>
    nameCodeKey(
      course.group_id,
      officialDisplayName(course, language),
      course.code,
    );
  const normalizedName = (language: DisplayLanguage) => {
    const name = officialDisplayName(course, language);
    return name === null ? null : normalizeLookup(name);
  };
  return {
    course,
    active: course.is_active,
    normalizedCode: normalizeLookup(course.code),
    normalizedName: { en: normalizedName("en"), fi: normalizedName("fi") },
    key: { en: key("en"), fi: key("fi") },
  };
}

function courseIndex(
  courses: readonly CatalogueCourse[],
): readonly CourseEntry[] {
  let index = courseIndexes.get(courses);
  if (index === undefined) {
    index = courses.map(buildCourseEntry);
    courseIndexes.set(courses, index);
  }
  return index;
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
  const rows: CourseEntry[] = [];
  for (const entry of courseIndex(courses)) {
    if (activeOnly && !entry.active) continue;
    const name = entry.normalizedName[language];
    if (
      !entry.normalizedCode.includes(normalizedQuery) &&
      !(name !== null && name.includes(normalizedQuery))
    )
      continue;
    rows.push(entry);
  }
  rows.sort((left, right) => {
    if (left.active !== right.active) return left.active ? -1 : 1;
    return compareKeys(left.key[language], right.key[language]);
  });
  return rows.map((row) => row.course);
}

type ModuleCandidate = CatalogueReport["modules"][number]["candidates"][number];

type CandidateEntry = {
  candidate: ModuleCandidate;
  normalizedCode: string;
  normalizedName: Record<DisplayLanguage, string | null>;
  key: Record<DisplayLanguage, SortKey>;
};

type ModuleEntry = {
  groupId: string;
  candidates: readonly ModuleCandidate[];
  /** Each language's candidates in the row's exact tie-break order. */
  ordered: Record<DisplayLanguage, readonly CandidateEntry[]>;
};

const moduleIndexes = new WeakMap<
  CatalogueReport["modules"],
  readonly ModuleEntry[]
>();

function buildCandidateEntry(
  groupId: string,
  candidate: ModuleCandidate,
): CandidateEntry {
  const key = (language: DisplayLanguage): SortKey =>
    nameCodeKey(
      groupId,
      officialDisplayName(candidate, language),
      candidate.code,
    );
  const normalizedName = (language: DisplayLanguage) => {
    const name = officialDisplayName(candidate, language);
    return name === null ? null : normalizeLookup(name);
  };
  return {
    candidate,
    normalizedCode: normalizeLookup(candidate.code ?? ""),
    normalizedName: { en: normalizedName("en"), fi: normalizedName("fi") },
    key: { en: key("en"), fi: key("fi") },
  };
}

function moduleIndex(
  modules: CatalogueReport["modules"],
): readonly ModuleEntry[] {
  let index = moduleIndexes.get(modules);
  if (index !== undefined) return index;
  index = modules.map((module) => {
    const candidates = module.candidates.map((candidate) =>
      buildCandidateEntry(module.group_id, candidate),
    );
    const order = (language: DisplayLanguage) =>
      [...candidates].sort((left, right) => {
        const keyOrder = compareKeys(left.key[language], right.key[language]);
        if (keyOrder !== 0) return keyOrder;
        return compareCodePoints(
          left.candidate.sisu_module_id,
          right.candidate.sisu_module_id,
        );
      });
    return {
      groupId: module.group_id,
      candidates: module.candidates,
      ordered: { en: order("en"), fi: order("fi") },
    };
  });
  moduleIndexes.set(modules, index);
  return index;
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
  const rows: {
    group: ModuleLookupGroup;
    programme: boolean;
    key: SortKey;
  }[] = [];
  for (const entry of moduleIndex(modules)) {
    let display: CandidateEntry | null = null;
    for (const candidate of entry.ordered[language]) {
      const name = candidate.normalizedName[language];
      if (
        candidate.normalizedCode.includes(normalizedQuery) ||
        (name !== null && name.includes(normalizedQuery))
      ) {
        display = candidate;
        break;
      }
    }
    if (display === null) continue;
    rows.push({
      group: {
        group_id: entry.groupId,
        module_type: display.candidate.module_type,
        code: display.candidate.code,
        name_fi: display.candidate.name_fi,
        name_en: display.candidate.name_en,
        candidates: entry.candidates,
      },
      programme: display.candidate.module_type === "DegreeProgramme",
      key: display.key[language],
    });
  }
  rows.sort((left, right) => {
    if (left.programme !== right.programme) return left.programme ? -1 : 1;
    return compareKeys(left.key, right.key);
  });
  return rows.map((row) => row.group);
}
