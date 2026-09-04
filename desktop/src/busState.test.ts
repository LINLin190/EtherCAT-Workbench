import { describe, expect, it } from "vitest";

import { minimumBusState } from "./busState";

describe("minimum bus state", () => {
  it("uses the lowest state across all slaves", () => {
    expect(minimumBusState([{ state: 8 }, { state: 2 }, { state: 8 }, { state: 8 }])).toBe(2);
  });

  it("reports a uniform state when every slave matches", () => {
    expect(minimumBusState([{ state: 4 }, { state: 4 }])).toBe(4);
  });

  it("has no state before slaves are discovered", () => {
    expect(minimumBusState([])).toBeUndefined();
  });
});
