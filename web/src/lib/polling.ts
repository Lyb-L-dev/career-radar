export function pollingInterval(
  active: boolean,
  hasError: boolean,
  activeIntervalMs: number,
): number | false {
  if (hasError) return 15_000
  return active ? activeIntervalMs : false
}
