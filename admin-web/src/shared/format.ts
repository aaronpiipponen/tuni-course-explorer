/**
 * Presentation helpers for the administration console's measured and nullable facts.
 *
 * Each helper renders the fact its owner reports. A nullable fact renders as the console's unknown
 * text rather than a substitute value.
 */
import { wording } from "./wording";

const BYTE_UNITS = ["B", "KiB", "MiB", "GiB", "TiB"];

/** Return the elapsed whole seconds, minutes, hours or days since one read. */
export function relativeAge(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  if (whole < 60) {
    return wording.ageSeconds.replace("{count}", String(whole));
  }
  if (whole < 3600) {
    return wording.ageMinutes.replace(
      "{count}",
      String(Math.floor(whole / 60)),
    );
  }
  if (whole < 86400) {
    const hours = Math.floor(whole / 3600);
    return hours === 1
      ? wording.ageHour
      : wording.ageHours.replace("{count}", String(hours));
  }
  const days = Math.floor(whole / 86400);
  return days === 1
    ? wording.ageDay
    : wording.ageDays.replace("{count}", String(days));
}

/** Render a byte count in its largest whole unit, or the unknown text when it is absent. */
export function humanBytes(bytes: number | null): string {
  if (bytes === null) {
    return wording.unknown;
  }
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  if (unit === 0) {
    return `${Math.round(value)} ${BYTE_UNITS[unit]}`;
  }
  return `${value.toFixed(1)} ${BYTE_UNITS[unit]}`;
}

/** Render a duration in at most three of its largest whole units. */
export function humanDuration(seconds: number | null): string {
  if (seconds === null) {
    return wording.unknown;
  }
  const whole = Math.max(0, Math.floor(seconds));
  const days = Math.floor(whole / 86400);
  const hours = Math.floor((whole % 86400) / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const remainder = whole % 60;
  if (days > 0) {
    return `${days} d ${hours} h ${minutes} m`;
  }
  if (hours > 0) {
    return `${hours} h ${minutes} m`;
  }
  if (minutes > 0) {
    return `${minutes} m ${remainder} s`;
  }
  return `${remainder} s`;
}

/** Render a whole count with its digit grouping, or the unknown text when it is absent. */
export function count(value: number | null): string {
  if (value === null) {
    return wording.unknown;
  }
  return value.toLocaleString("en-US");
}

/** Render a timestamp in UTC as a date and a whole minute. */
export function moment(value: string | null): string {
  if (value === null) {
    return wording.unknown;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return wording.unknown;
  }
  return parsed.toISOString().slice(0, 16).replace("T", " ");
}

/** Render one measured elapsed duration in seconds to two decimals. */
export function shortDuration(seconds: number): string {
  return `${seconds.toFixed(2)} s`;
}

/** Render one measured rate, or the unknown text when the owner reports none. */
export function rate(itemsPerSecond: number | null): string {
  if (itemsPerSecond === null) {
    return wording.unknown;
  }
  return `${itemsPerSecond.toFixed(2)}/s`;
}

/** Return the whole percentage one completed count is of its total. */
export function percent(done: number, total: number): number {
  if (total <= 0) {
    return 0;
  }
  return Math.round((done / total) * 100);
}

/** Render one lifecycle or state word, or the unknown text when the owner reports none. */
export function stateText(value: string | null): string {
  return value === null || value === "" ? wording.unknown : value;
}
