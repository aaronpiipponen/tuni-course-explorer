/** Dataset scoping and least-recently-used eviction of the app-level read cache. */
import { describe, expect, it } from "vitest";
import { ReadCache } from "./readCache";

describe("read cache", () => {
  it("isolates cached reads by serving dataset identity", () => {
    const cache = new ReadCache("dataset-one", 4);
    cache.put("dataset-one", "prerequisites:root", { payload: "first" });
    expect(cache.get<{ payload: string }>("prerequisites:root")).toEqual({
      payload: "first",
    });
    expect(cache.get("course-summaries:root")).toBeUndefined();

    cache.put("dataset-two", "course-summaries:root", { payload: "second" });
    expect(cache.getDatasetIdentity()).toBe("dataset-two");
    expect(cache.get("prerequisites:root")).toBeUndefined();
    expect(cache.get<{ payload: string }>("course-summaries:root")).toEqual({
      payload: "second",
    });
  });

  it("evicts the least recently used read at capacity", () => {
    const cache = new ReadCache("dataset-one", 3);
    cache.put("dataset-one", "first", 1);
    cache.put("dataset-one", "second", 2);
    cache.put("dataset-one", "third", 3);

    // A hit refreshes recency, so the untouched entry is the least recently used.
    expect(cache.get("first")).toBe(1);
    cache.put("dataset-one", "fourth", 4);
    expect(cache.get("second")).toBeUndefined();
    expect(cache.get("first")).toBe(1);
    expect(cache.get("third")).toBe(3);
    expect(cache.get("fourth")).toBe(4);

    // Replacing a key updates its value without taking a second slot.
    cache.put("dataset-one", "third", 30);
    expect(cache.get("third")).toBe(30);
    cache.put("dataset-one", "fifth", 5);
    expect(cache.get("first")).toBeUndefined();
    expect(cache.get("third")).toBe(30);
    expect(cache.get("fourth")).toBe(4);
    expect(cache.get("fifth")).toBe(5);
  });
});
