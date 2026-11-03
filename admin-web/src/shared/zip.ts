/**
 * Build one stored (uncompressed) ZIP archive from named byte arrays.
 *
 * The console gathers a submission's attachments in the browser and saves them as one archive, so
 * no additional backend route exists. Entries use the UTF-8 name flag and the store method, which
 * suit the small PNG and JPEG files the feedback inbox holds. Repeated filenames are made distinct
 * so extraction never overwrites one attachment with another.
 */

/** One archive entry: the filename shown on extraction and the bytes it carries. */
export interface ZipEntry {
  name: string;
  data: Uint8Array;
}

const LOCAL_FILE_HEADER = 0x04034b50;
const CENTRAL_DIRECTORY_HEADER = 0x02014b50;
const END_OF_CENTRAL_DIRECTORY = 0x06054b50;
const UTF8_FLAG = 0x0800;
const STORE_METHOD = 0;
const VERSION = 20;
// One fixed 1980-01-01 timestamp keeps the archive deterministic.
const DOS_TIME = 0;
const DOS_DATE = (1 << 5) | 1;

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let index = 0; index < 256; index += 1) {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) {
      value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    }
    table[index] = value >>> 0;
  }
  return table;
})();

function crc32(data: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc = (crc >>> 8) ^ CRC_TABLE[(crc ^ byte) & 0xff];
  }
  return (crc ^ 0xffffffff) >>> 0;
}

/** Return the entry names with later duplicates suffixed as `name-2.ext`. */
function distinctNames(names: readonly string[]): string[] {
  const used = new Set<string>();
  return names.map((name) => {
    const dot = name.lastIndexOf(".");
    const stem = dot > 0 ? name.slice(0, dot) : name;
    const suffix = dot > 0 ? name.slice(dot) : "";
    let candidate = name;
    let index = 2;
    while (used.has(candidate.toLowerCase())) {
      candidate = `${stem}-${index}${suffix}`;
      index += 1;
    }
    used.add(candidate.toLowerCase());
    return candidate;
  });
}

/** Build one archive from the entries in their given order. */
export function buildZip(entries: readonly ZipEntry[]): Blob {
  const encoder = new TextEncoder();
  const names = distinctNames(entries.map((entry) => entry.name));
  const prepared = entries.map((entry, index) => ({
    name: encoder.encode(names[index]),
    data: entry.data,
    crc: crc32(entry.data),
    offset: 0,
  }));
  let size = 22;
  for (const entry of prepared) {
    size += 30 + entry.name.length + entry.data.length;
    size += 46 + entry.name.length;
  }
  const output = new Uint8Array(size);
  const view = new DataView(output.buffer);
  let at = 0;
  const u16 = (value: number): void => {
    view.setUint16(at, value, true);
    at += 2;
  };
  const u32 = (value: number): void => {
    view.setUint32(at, value, true);
    at += 4;
  };
  const bytes = (value: Uint8Array): void => {
    output.set(value, at);
    at += value.length;
  };

  for (const entry of prepared) {
    entry.offset = at;
    u32(LOCAL_FILE_HEADER);
    u16(VERSION);
    u16(UTF8_FLAG);
    u16(STORE_METHOD);
    u16(DOS_TIME);
    u16(DOS_DATE);
    u32(entry.crc);
    u32(entry.data.length);
    u32(entry.data.length);
    u16(entry.name.length);
    u16(0);
    bytes(entry.name);
    bytes(entry.data);
  }

  const centralStart = at;
  for (const entry of prepared) {
    u32(CENTRAL_DIRECTORY_HEADER);
    u16(VERSION);
    u16(VERSION);
    u16(UTF8_FLAG);
    u16(STORE_METHOD);
    u16(DOS_TIME);
    u16(DOS_DATE);
    u32(entry.crc);
    u32(entry.data.length);
    u32(entry.data.length);
    u16(entry.name.length);
    u16(0);
    u16(0);
    u16(0);
    u16(0);
    u32(0);
    u32(entry.offset);
    bytes(entry.name);
  }
  const centralSize = at - centralStart;

  u32(END_OF_CENTRAL_DIRECTORY);
  u16(0);
  u16(0);
  u16(prepared.length);
  u16(prepared.length);
  u32(centralSize);
  u32(centralStart);
  u16(0);

  return new Blob([output], { type: "application/zip" });
}
