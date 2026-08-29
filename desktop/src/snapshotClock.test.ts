import { describe, expect, it } from "vitest";

import { acceptsSessionEvent, acceptsSnapshot, type SnapshotClock } from "./snapshotClock";

const clock = (
  host_generation: number,
  session_id: number,
  revision: number,
): SnapshotClock => ({ host_generation, session_id, revision });

describe("snapshot clock ordering", () => {
  it("rejects an older revision from the same host generation and session", () => {
    expect(acceptsSnapshot(clock(4, 8, 12), clock(4, 8, 11))).toBe(false);
  });

  it("rejects an expired session even when its revision is larger", () => {
    expect(acceptsSnapshot(clock(4, 8, 2), clock(4, 7, 999))).toBe(false);
  });

  it("accepts a new session whose revision restarted", () => {
    expect(acceptsSnapshot(clock(4, 8, 999), clock(4, 9, 1))).toBe(true);
  });

  it("rejects every snapshot from an older host generation", () => {
    expect(acceptsSnapshot(clock(5, 0, 0), clock(4, 999, 999))).toBe(false);
  });

  it("accepts a replacement host generation starting from zero", () => {
    expect(acceptsSnapshot(clock(4, 99, 99), clock(5, 0, 0))).toBe(true);
  });

  it("rejects process events from an expired session or host generation", () => {
    const current = clock(5, 3, 8);
    expect(acceptsSessionEvent(current, { host_generation: 5, session_id: 2 })).toBe(false);
    expect(acceptsSessionEvent(current, { host_generation: 4, session_id: 3 })).toBe(false);
    expect(acceptsSessionEvent(current, { host_generation: 5, session_id: 3 })).toBe(true);
  });
});
