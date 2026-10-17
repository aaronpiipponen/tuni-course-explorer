/**
 * One current-shape validation boundary for the stored browser envelope, the typed profile and
 * whole-state files, and the pending Sisu capture a profile holds.
 *
 * A supplied field is checked before it is used, and an unknown field is dropped.
 * An absent profile field reads from its default. A supplied structure requires its ordered
 * programme list. Validation checks shape and types rather than catalogue membership: a
 * course identity is accepted as the string it is.
 */
import { initialProfileState } from "./defaults";
import type {
  BrowserState,
  DisplayLanguage,
  Profile,
  ProfileState,
} from "./types";
import { initialCompareState } from "../features/compare/state";
import { initialDiscoverState } from "../features/discover/state";
import { initialPrerequisitesState } from "../features/prerequisites/state";
import { initialSearchState } from "../features/search/state";
import {
  initialStructureState,
  type StructureChoices,
} from "../features/structure/state";
import { validateSisuPlan } from "../features/structure/sisu";

const STATE_MESSAGE = "Saved browser profile state is invalid";
const PROFILE_MESSAGE = "Saved browser profile is invalid";
const ENVELOPE_MESSAGE = "Saved browser state is invalid";

const LANGUAGES = ["fi", "en"] as const;

type SliceKey =
  "search" | "compare" | "prerequisites" | "discover" | "structure";

function sliceMessage(key: SliceKey): string {
  return `Saved browser profile slice ${key} is invalid`;
}

function objectValue(value: unknown, message: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error(message);
  return value as Record<string, unknown>;
}

function stringField(value: unknown, message: string): string {
  if (typeof value !== "string") throw new Error(message);
  return value;
}

function booleanField(value: unknown, message: string): boolean {
  if (typeof value !== "boolean") throw new Error(message);
  return value;
}

function identity(value: unknown, message: string): string {
  if (typeof value !== "string" || value === "") throw new Error(message);
  return value;
}

function nullableIdentity(value: unknown, message: string): string | null {
  if (value === null) return null;
  return identity(value, message);
}

function literalField<T extends string>(
  value: unknown,
  allowed: readonly T[],
  message: string,
): T {
  if (typeof value !== "string" || !allowed.includes(value as T))
    throw new Error(message);
  return value as T;
}

function identityArray(value: unknown, message: string): string[] {
  if (!Array.isArray(value)) throw new Error(message);
  return value.map((item) => identity(item, message));
}

function uniqueIdentityArray(value: unknown, message: string): string[] {
  const ids = identityArray(value, message);
  if (new Set(ids).size !== ids.length) throw new Error(message);
  return ids;
}

function projectSearch(value: unknown) {
  const message = sliceMessage("search");
  const saved = objectValue(value, message);
  const defaults = initialSearchState();
  return {
    query:
      saved.query === undefined
        ? defaults.query
        : stringField(saved.query, message),
    activeOnly:
      saved.activeOnly === undefined
        ? defaults.activeOnly
        : booleanField(saved.activeOnly, message),
  };
}

function projectCompare(value: unknown) {
  const message = sliceMessage("compare");
  const saved = objectValue(value, message);
  const defaults = initialCompareState();
  let slots: [string | null, string | null] = [
    defaults.slots[0],
    defaults.slots[1],
  ];
  if (saved.slots !== undefined) {
    if (!Array.isArray(saved.slots) || saved.slots.length !== 2)
      throw new Error(message);
    const [first, second] = saved.slots;
    const left = nullableIdentity(first, message);
    const right = nullableIdentity(second, message);
    if (left !== null && left === right) throw new Error(message);
    slots = [left, right];
  }
  return {
    slots,
    pickerQuery:
      saved.pickerQuery === undefined
        ? defaults.pickerQuery
        : stringField(saved.pickerQuery, message),
    pickerActiveOnly:
      saved.pickerActiveOnly === undefined
        ? defaults.pickerActiveOnly
        : booleanField(saved.pickerActiveOnly, message),
  };
}

function projectPrerequisites(value: unknown) {
  const message = sliceMessage("prerequisites");
  const saved = objectValue(value, message);
  const defaults = initialPrerequisitesState();
  return {
    rootCourseId:
      saved.rootCourseId === undefined
        ? null
        : nullableIdentity(saved.rootCourseId, message),
    courseQuery:
      saved.courseQuery === undefined
        ? defaults.courseQuery
        : stringField(saved.courseQuery, message),
    includeRecommended:
      saved.includeRecommended === undefined
        ? defaults.includeRecommended
        : booleanField(saved.includeRecommended, message),
    includeInferred:
      saved.includeInferred === undefined
        ? defaults.includeInferred
        : booleanField(saved.includeInferred, message),
    activeOnly:
      saved.activeOnly === undefined
        ? defaults.activeOnly
        : booleanField(saved.activeOnly, message),
    basis:
      saved.basis === undefined
        ? defaults.basis
        : literalField(
            saved.basis,
            ["completed", "selected"] as const,
            message,
          ),
    excludedCourseIds:
      saved.excludedCourseIds === undefined
        ? []
        : identityArray(saved.excludedCourseIds, message),
    completedNodeKeys:
      saved.completedNodeKeys === undefined
        ? []
        : identityArray(saved.completedNodeKeys, message),
    excludedNodeKeys:
      saved.excludedNodeKeys === undefined
        ? []
        : identityArray(saved.excludedNodeKeys, message),
  };
}

function projectDiscover(value: unknown) {
  const message = sliceMessage("discover");
  const saved = objectValue(value, message);
  const defaults = initialDiscoverState();
  return {
    list:
      saved.list === undefined
        ? defaults.list
        : literalField(saved.list, ["next", "recommended"] as const, message),
    mode:
      saved.mode === undefined
        ? defaults.mode
        : literalField(saved.mode, ["all", "at_least_one"] as const, message),
    activeOnly:
      saved.activeOnly === undefined
        ? defaults.activeOnly
        : booleanField(saved.activeOnly, message),
    basis:
      saved.basis === undefined
        ? defaults.basis
        : literalField(
            saved.basis,
            ["completed", "selected"] as const,
            message,
          ),
    basisExpanded:
      saved.basisExpanded === undefined
        ? defaults.basisExpanded
        : booleanField(saved.basisExpanded, message),
  };
}

function choicesField(value: unknown, message: string): StructureChoices {
  const saved = objectValue(value, message);
  return Object.fromEntries(
    Object.entries(saved).map(([key, options]) => [
      identity(key, message),
      identityArray(options, message),
    ]),
  );
}

function placementsField(
  value: unknown,
  message: string,
): Record<string, string | null> {
  const saved = objectValue(value, message);
  return Object.fromEntries(
    Object.entries(saved).map(([key, target]) => [
      identity(key, message),
      nullableIdentity(target, message),
    ]),
  );
}

function projectStructure(value: unknown) {
  const message = sliceMessage("structure");
  const saved = objectValue(value, message);
  return {
    // The ordered programme list is the structure's top-level identity, so a supplied
    // structure object without it is not a readable structure.
    programmeGroupIds: uniqueIdentityArray(saved.programmeGroupIds, message),
    choices:
      saved.choices === undefined ? {} : choicesField(saved.choices, message),
    coursePlacements:
      saved.coursePlacements === undefined
        ? {}
        : placementsField(saved.coursePlacements, message),
    modulePlacements:
      saved.modulePlacements === undefined
        ? {}
        : placementsField(saved.modulePlacements, message),
    placedCourseIds:
      saved.placedCourseIds === undefined
        ? []
        : uniqueIdentityArray(saved.placedCourseIds, message),
  };
}

/**
 * Validate one profile state, filling absent profile fields from their defaults.
 *
 * A supplied structure requires its ordered programme list. Unknown fields are dropped.
 */
export function validateProfileState(value: unknown): ProfileState {
  const saved = objectValue(value, STATE_MESSAGE);
  const defaults = initialProfileState();
  const selectedCourseIds =
    saved.selectedCourseIds === undefined
      ? []
      : uniqueIdentityArray(saved.selectedCourseIds, STATE_MESSAGE);
  const completedCourseIds =
    saved.completedCourseIds === undefined
      ? []
      : uniqueIdentityArray(saved.completedCourseIds, STATE_MESSAGE);
  for (const id of completedCourseIds)
    if (!selectedCourseIds.includes(id)) throw new Error(STATE_MESSAGE);
  return {
    language:
      saved.language === undefined
        ? defaults.language
        : literalField<DisplayLanguage>(
            saved.language,
            LANGUAGES,
            STATE_MESSAGE,
          ),
    selectedCourseIds,
    completedCourseIds,
    search:
      saved.search === undefined
        ? initialSearchState()
        : projectSearch(saved.search),
    compare:
      saved.compare === undefined
        ? initialCompareState()
        : projectCompare(saved.compare),
    prerequisites:
      saved.prerequisites === undefined
        ? initialPrerequisitesState()
        : projectPrerequisites(saved.prerequisites),
    discover:
      saved.discover === undefined
        ? initialDiscoverState()
        : projectDiscover(saved.discover),
    structure:
      saved.structure === undefined
        ? initialStructureState()
        : projectStructure(saved.structure),
    pendingSisuImport:
      saved.pendingSisuImport === undefined || saved.pendingSisuImport === null
        ? null
        : validateSisuPlan(saved.pendingSisuImport),
  };
}

/** Reject a profile whose name is not a string, is blank, or carries surrounding whitespace. */
export function validateProfile(value: unknown): Profile {
  const saved = objectValue(value, PROFILE_MESSAGE);
  if (
    typeof saved.name !== "string" ||
    saved.name.trim() === "" ||
    saved.name !== saved.name.trim()
  )
    throw new Error(PROFILE_MESSAGE);
  return { name: saved.name, state: validateProfileState(saved.state) };
}

/**
 * Validate one stored envelope of schema version 2.
 *
 * Every profile is validated, the current profile must exist, and profile names must be unique.
 */
export function validateBrowserState(value: unknown): BrowserState {
  const saved = objectValue(value, ENVELOPE_MESSAGE);
  if (saved.schemaVersion !== 2)
    throw new Error("Unsupported saved browser state schema");
  if (
    typeof saved.currentProfileId !== "string" ||
    saved.currentProfileId === "" ||
    !saved.profiles ||
    typeof saved.profiles !== "object" ||
    Array.isArray(saved.profiles)
  )
    throw new Error("Saved browser state has no current profile");
  const profiles = Object.fromEntries(
    Object.entries(saved.profiles as Record<string, unknown>).map(
      ([id, profile]) => [
        identity(id, PROFILE_MESSAGE),
        validateProfile(profile),
      ],
    ),
  );
  const ids = Object.keys(profiles);
  if (ids.length === 0 || !Object.hasOwn(profiles, saved.currentProfileId))
    throw new Error("Saved browser state has no current profile");
  const names = new Set(ids.map((id) => profiles[id].name));
  if (names.size !== ids.length) throw new Error(ENVELOPE_MESSAGE);
  return {
    schemaVersion: 2,
    currentProfileId: saved.currentProfileId,
    profiles,
  };
}
