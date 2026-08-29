export interface SnapshotClock {
  host_generation: number;
  session_id: number;
  revision: number;
}

export interface SessionEventClock {
  host_generation?: number;
  session_id?: number;
}

export function compareSnapshotClock(left: SnapshotClock, right: SnapshotClock): number {
  if (left.host_generation !== right.host_generation) {
    return left.host_generation - right.host_generation;
  }
  if (left.session_id !== right.session_id) {
    return left.session_id - right.session_id;
  }
  return left.revision - right.revision;
}

export function acceptsSnapshot(current: SnapshotClock | undefined, incoming: SnapshotClock): boolean {
  return current === undefined || compareSnapshotClock(incoming, current) >= 0;
}

export function acceptsSessionEvent(
  current: SnapshotClock | undefined,
  event: SessionEventClock,
): boolean {
  if (event.session_id === undefined) return true;
  return current !== undefined
    && event.host_generation === current.host_generation
    && event.session_id === current.session_id;
}
