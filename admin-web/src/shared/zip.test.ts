/**
 * Archive-layout proofs for the stored ZIP writer the feedback download uses.
 *
 * The proof builds one archive of two entries, reads its bytes back and walks the central
 * directory, so each entry's name, method, declared size and stored bytes are read the way a ZIP
 * reader finds them.
 */
import { describe, expect, it } from "vitest";
import { buildZip } from "./zip";

const LOCAL_FILE_HEADER = 0x04034b50;
const CENTRAL_DIRECTORY_HEADER = 0x02014b50;
const END_OF_CENTRAL_DIRECTORY = 0x06054b50;
const STORE_METHOD = 0;

describe("buildZip", () => {
  it("writes stored entries that a ZIP reader lists with their names and bytes", async () => {
    const first = new TextEncoder().encode("first entry bytes");
    const second = new Uint8Array([0, 1, 2, 250, 255]);
    const archive = buildZip([
      { name: "alpha.png", data: first },
      { name: "beta.jpg", data: second },
    ]);
    const view = new DataView(await archive.arrayBuffer());
    const decoder = new TextDecoder();
    const read = (offset: number, length: number): Uint8Array =>
      new Uint8Array(view.buffer, offset, length);

    // The end record closes the archive and names the central directory.
    const end = view.byteLength - 22;
    expect(view.getUint32(end, true)).toBe(END_OF_CENTRAL_DIRECTORY);
    const entryCount = view.getUint16(end + 10, true);
    const directorySize = view.getUint32(end + 12, true);
    const directoryStart = view.getUint32(end + 16, true);
    expect(entryCount).toBe(2);

    let at = directoryStart;
    const entries: { name: string; data: Uint8Array }[] = [];
    for (let index = 0; index < entryCount; index += 1) {
      expect(view.getUint32(at, true)).toBe(CENTRAL_DIRECTORY_HEADER);
      expect(view.getUint16(at + 10, true)).toBe(STORE_METHOD);
      const size = view.getUint32(at + 24, true);
      const nameLength = view.getUint16(at + 28, true);
      const extraLength = view.getUint16(at + 30, true);
      const commentLength = view.getUint16(at + 32, true);
      const localOffset = view.getUint32(at + 42, true);

      expect(view.getUint32(localOffset, true)).toBe(LOCAL_FILE_HEADER);
      const localNameLength = view.getUint16(localOffset + 26, true);
      const localExtraLength = view.getUint16(localOffset + 28, true);
      const dataStart = localOffset + 30 + localNameLength + localExtraLength;
      entries.push({
        name: decoder.decode(read(at + 46, nameLength)),
        data: read(dataStart, size),
      });
      at += 46 + nameLength + extraLength + commentLength;
    }

    // The walk consumes exactly the declared directory.
    expect(at - directoryStart).toBe(directorySize);
    expect(entries.map((entry) => entry.name)).toEqual([
      "alpha.png",
      "beta.jpg",
    ]);
    expect([...entries[0].data]).toEqual([...first]);
    expect([...entries[1].data]).toEqual([...second]);
  });
});
