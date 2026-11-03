/**
 * Pure geometry extraction of one supported Sisu plan PDF's positioned text into ordered plan rows.
 *
 * The extractor reads page coordinates only. It imports neither the PDF decoder nor the network or
 * browser storage, so the row rules run from synthetic positioned items. The supported print uses a
 * left name and code column, a status and credit column, small body text and one print layout per
 * page. Rows are grouped by baseline, merged in document order and classified as course or module.
 */
import { normalizeSisuName } from "./sisuNames";

/** Safe failure message of an unsupported or unreadable Sisu PDF plan. */
export const INVALID_SISU_PDF_PLAN = "Invalid Sisu PDF plan";

/** One positioned text item as the decoder reports it. */
export type SisuPdfTextItem = {
  str: string;
  transform: readonly number[];
  width: number;
  height: number;
};

/** One page of positioned text items. */
export type SisuPdfTextPage = {
  page: number;
  items: readonly SisuPdfTextItem[];
};

/** One recognized plan row: a course entry or a module heading. */
export type SisuPdfRow = {
  kind: "course" | "module";
  code: string | null;
  name: string;
  completed: boolean;
  x: number;
};

/** The greatest text height in PDF points that a body item may hold. */
const BODY_MAX_HEIGHT = 9;
/** The lowest body item baseline in PDF points from the page bottom. */
const BODY_MIN_BASELINE = 30;
/** The highest body item baseline in PDF points from the page bottom on page one. */
const FIRST_PAGE_MAX_BASELINE = 540;
/** The highest body item baseline in PDF points from the page bottom on a later page. */
const LATER_PAGE_MAX_BASELINE = 770;
/** The x coordinate in PDF points that splits the name column from the status column. */
const COLUMN_SPLIT_X = 200;
/** The baseline bucket in PDF points that groups items into one printed row. */
const BASELINE_BUCKET = 2;
/** The indent tolerance in PDF points that separates one print level from the next. */
export const INDENT_TOLERANCE = 1;
/** The gap share of the text height above which a word space is inserted. */
const WORD_GAP_RATIO = 0.2;

const CODE =
  /^[A-ZÅÄÖ0-9][A-ZÅÄÖ0-9.\-]*[A-ZÅÄÖ0-9](?:\.[A-ZÅÄÖ0-9.\-]+)*(?=\s|$)/;
const CREDIT =
  /(?<![\d-])\d+\s*(?:–\s*\d+\s*)?(?:\/\s*(?:väh\.|min\.|\d)|op\b|cr\b)/;
const DATE = /\d{1,2}\.\d{1,2}\.\d{4}/;
const ACADEMIC_RANGE = /\d{4}-\d{4}/;

const STATUS_FRAGMENTS = [
  "Valinnat tehty",
  "Valinnat kesken",
  "Osat suoritettu",
  "Epäsuoria valintoja",
  "Vapaaehtoisia valintoja",
  "Sääntöjen",
  "vastainen",
  "Vaatii erillistä",
  "hyväksyntää",
  "/ väh.",
  "valintoja",
  "Vapaaehtoisia",
  "Selections done",
  "Selections incomplete",
  "Selections",
  "Parts completed",
  "Optional selections",
  "Optional",
  "Indirect selections",
  "Indirect",
  "Against the rules",
  "Approval required",
  "Approval",
  "min.",
];

const FULL_STATUSES = [
  "Valinnat tehty",
  "Valinnat kesken",
  "Osat suoritettu",
  "Epäsuoria valintoja",
  "Vapaaehtoisia valintoja",
  "Sääntöjen vastainen",
  "Vaatii erillistä hyväksyntää",
  "Selections done",
  "Selections incomplete",
  "Parts completed",
  "Optional selections",
  "Indirect selections",
  "Against the rules",
  "Approval required",
];

/** Return whether one item belongs to the plan body rather than a title, header or footer. */
function isBodyItem(item: SisuPdfTextItem, page: number): boolean {
  if (item.str.trim() === "") return false;
  if (item.height <= 0 || item.height > BODY_MAX_HEIGHT) return false;
  const baseline = item.transform[5];
  if (baseline < BODY_MIN_BASELINE) return false;
  return page === 1
    ? baseline <= FIRST_PAGE_MAX_BASELINE
    : baseline <= LATER_PAGE_MAX_BASELINE;
}

/** Return whether one left-column text starts an entry rather than continuing the previous row. */
function startsEntry(left: string, tail: string): boolean {
  const token = CODE.exec(left)?.[0];
  if (token === undefined) return false;
  const rest = normalizeSisuName(left.slice(token.length));
  // A letters-only word such as an upper-case course-name fragment starts an entry only when the
  // status cell proves the row is a module heading.
  if (!/[0-9.\-]/.test(token) && !isModuleTail(tail)) return false;
  if (rest !== "") return true;
  return token.includes(".") || token.includes("-") || isModuleTail(tail);
}

/** Return whether one status cell names a module status. */
function isModuleTail(tail: string): boolean {
  return STATUS_FRAGMENTS.some((fragment) => tail.includes(fragment));
}

/** Return whether one status cell holds a complete module status. */
function isFullStatus(tail: string): boolean {
  return FULL_STATUSES.some((status) => tail.includes(status));
}

/**
 * Merge one row's text runs in x order, inserting a word space only where the geometric gap between
 * two runs is wider than a fifth of their text height.
 */
function mergeRuns(items: readonly SisuPdfTextItem[]): string {
  let text = "";
  let previousRight: number | null = null;
  let previousHeight = 0;
  for (const item of [...items].sort(
    (left, right) => left.transform[4] - right.transform[4],
  )) {
    const str = normalizeSisuName(item.str);
    if (str === "") continue;
    if (
      text !== "" &&
      previousRight !== null &&
      !text.endsWith(" ") &&
      !str.startsWith(" ") &&
      item.transform[4] - previousRight >
        WORD_GAP_RATIO * Math.max(previousHeight, item.height)
    )
      text += " ";
    text += str;
    previousRight = item.transform[4] + item.width;
    previousHeight = item.height;
  }
  return normalizeSisuName(text);
}

/** One baseline group before entry merging. */
type RawRow = {
  page: number;
  y: number;
  left: string;
  tail: string;
  x: number;
};

/** Group each page's body items by baseline and split them into the name and status columns. */
function rawRows(pages: readonly SisuPdfTextPage[]): RawRow[] {
  const rows: RawRow[] = [];
  for (const page of pages) {
    const groups = new Map<number, SisuPdfTextItem[]>();
    for (const item of page.items) {
      if (!isBodyItem(item, page.page)) continue;
      const bucket =
        Math.round(item.transform[5] / BASELINE_BUCKET) * BASELINE_BUCKET;
      const group = groups.get(bucket);
      if (group) group.push(item);
      else groups.set(bucket, [item]);
    }
    for (const [y, items] of groups) {
      const leftItems = items.filter(
        (item) => item.transform[4] < COLUMN_SPLIT_X,
      );
      const tailItems = items.filter(
        (item) => item.transform[4] >= COLUMN_SPLIT_X,
      );
      const left = mergeRuns(leftItems);
      if (left === "") continue;
      rows.push({
        page: page.page,
        y,
        left,
        tail: mergeRuns(tailItems),
        x: Math.min(...leftItems.map((item) => item.transform[4])),
      });
    }
  }
  return rows.sort((left, right) => left.page - right.page || right.y - left.y);
}

/** One entry accumulated from one or more printed rows. */
type Entry = {
  x: number;
  left: string;
  tail: string;
};

/** Return whether one raw row starts a new entry rather than continuing the previous one. */
function rowStartsEntry(row: RawRow, previous: Entry | undefined): boolean {
  if (startsEntry(row.left, row.tail)) return true;
  if (row.left && isFullStatus(row.tail)) return true;
  if (!CREDIT.test(row.tail) || ACADEMIC_RANGE.test(row.tail)) return false;
  if (
    !previous ||
    Math.abs(previous.x - row.x) > INDENT_TOLERANCE ||
    !isModuleTail(previous.tail)
  )
    return true;
  if (
    CODE.test(previous.left) &&
    CODE.exec(previous.left)?.[0] === previous.left
  )
    return false;
  if (/^[a-zåäö]/.test(row.left)) return false;
  return isFullStatus(row.tail);
}

/** Join one continuation row to its entry, without a space after a joined hyphen. */
function joinContinuation(entry: Entry, row: RawRow): void {
  const firstWord = row.left.split(" ")[0];
  const joiner =
    entry.left.endsWith("-") &&
    !entry.left.endsWith(" -") &&
    /^[a-zåäö]/.test(row.left) &&
    firstWord !== "ja" &&
    firstWord !== "tai"
      ? ""
      : " ";
  entry.left = normalizeSisuName(entry.left + joiner + row.left);
  entry.tail = normalizeSisuName(`${entry.tail} ${row.tail}`);
}

/** Merge wrapped rows, page breaks and outdented continuation rows into ordered entries. */
function entries(rows: readonly RawRow[]): Entry[] {
  const merged: Entry[] = [];
  for (const row of rows) {
    const previous = merged[merged.length - 1];
    if (rowStartsEntry(row, previous)) {
      merged.push({
        x: row.x,
        left: row.left,
        tail: row.tail,
      });
      continue;
    }
    if (previous) joinContinuation(previous, row);
  }
  return merged;
}

/** Classify one merged entry into the plan row the matcher consumes. */
function classify(entry: Entry): SisuPdfRow {
  const code = CODE.exec(entry.left)?.[0] ?? null;
  const name = normalizeSisuName(
    code === null ? entry.left : entry.left.slice(code.length),
  );
  const kind = isModuleTail(entry.tail) ? "module" : "course";
  return {
    kind,
    code,
    name: name === "" && code !== null ? code : name,
    completed: kind === "course" && DATE.test(entry.tail),
    x: entry.x,
  };
}

/** Extract the ordered plan rows one supported Sisu plan print yields. */
export function extractSisuPdfRows(
  pages: readonly SisuPdfTextPage[],
): readonly SisuPdfRow[] {
  return entries(rawRows(pages)).map(classify);
}
