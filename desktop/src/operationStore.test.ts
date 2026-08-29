import { beforeEach, describe, expect, it, vi } from "vitest";

let operationStore: typeof import("./operationStore").operationStore;

beforeEach(async () => {
  vi.resetModules();
  ({ operationStore } = await import("./operationStore"));
});

describe("operation store lifecycle boundaries", () => {
  it("invalidates the old page request but not a request started after navigation", () => {
    const oldRequest = operationStore.begin("register_catalog");
    operationStore.transition(oldRequest.id, "running");

    operationStore.nextPage();
    expect(operationStore.get(oldRequest.id)?.phase).toBe("failed");

    const newRequest = operationStore.begin("register_catalog");
    operationStore.transition(newRequest.id, "running");
    expect(operationStore.get(newRequest.id)?.phase).toBe("running");
  });

  it("keeps the response source alive when a replacement host generation arrives", () => {
    operationStore.setSnapshotClock(1, 1);
    const status = operationStore.begin("status");
    const registerRead = operationStore.begin("register_read");
    operationStore.transition(status.id, "running");
    operationStore.transition(registerRead.id, "running");

    operationStore.setSnapshotClock(2, 0, status.id);

    expect(operationStore.get(status.id)?.phase).toBe("running");
    expect(operationStore.get(registerRead.id)?.phase).toBe("failed");
  });
});
