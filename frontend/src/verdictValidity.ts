// Presentation guard only; the backend alone determines the safety verdict.
export function verdictExpired(validUntil: string, now: number): boolean {
  const deadline = Date.parse(validUntil);
  return !Number.isFinite(deadline) || !Number.isFinite(now) || now >= deadline;
}
