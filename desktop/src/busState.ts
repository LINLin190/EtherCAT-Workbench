import type { SlaveInfo } from "./types";

export function minimumBusState(slaves: Pick<SlaveInfo, "state">[]): number | undefined {
  if (!slaves.length) return undefined;
  return Math.min(...slaves.map((slave) => slave.state));
}
