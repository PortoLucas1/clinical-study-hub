/** Reshape long rows (x, series, value) into wide rows ({x, [series]: value}) for AppKit charts. */
export function pivot<T extends Record<string, unknown>>(
  rows: T[],
  xKey: Extract<keyof T, string>,
  seriesKey: Extract<keyof T, string>,
  valueKey: Extract<keyof T, string>,
  opts?: { fill?: 'zero' | 'forward' },
): { data: Record<string, string | number>[]; series: string[] } {
  const series: string[] = [];
  const byX = new Map<string, Record<string, string | number>>();
  for (const row of rows) {
    const x = String(row[xKey]);
    const s = String(row[seriesKey]);
    if (!series.includes(s)) series.push(s);
    const entry = byX.get(x) ?? { [xKey]: x };
    entry[s] = Number(row[valueKey] ?? 0);
    byX.set(x, entry);
  }
  const last: Record<string, number> = {};
  const data = [...byX.values()].map((entry) => {
    for (const s of series) {
      if (s in entry) last[s] = Number(entry[s]);
      else entry[s] = opts?.fill === 'forward' ? (last[s] ?? 0) : 0;
    }
    return entry;
  });
  return { data, series };
}
