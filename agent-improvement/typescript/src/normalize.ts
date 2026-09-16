/**
 * Normalization helpers for messy IDs and dates.
 *
 * DB + external services return mixed formats:
 *   IDs:  "c123" vs "C123" vs " C123 "
 *   Dates: "2026-08-14" vs "08/14/26" vs "Aug 14 2026" vs "11/30/25"
 *
 * Candidate TODO: use these everywhere tool outputs are built so the model
 * always sees canonical forms (upper IDs, ISO dates). Extend as needed.
 */

const MONTHS: Record<string, number> = {
  jan: 1, january: 1, feb: 2, february: 2, mar: 3, march: 3,
  apr: 4, april: 4, may: 5, jun: 6, june: 6, jul: 7, july: 7,
  aug: 8, august: 8, sep: 9, sept: 9, september: 9,
  oct: 10, october: 10, nov: 11, november: 11, dec: 12, december: 12,
};

export function normalizeId(value: string): string {
  return value.trim().toUpperCase();
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** Parse the known mixed formats. Returns null if unparseable. */
export function parseDate(value: string): Date | null {
  const text = value.trim();
  // YYYY-MM-DD
  let m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(text);
  if (m) return new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  // MM/DD/YY or MM/DD/YYYY
  m = /^(\d{1,2})\/(\d{1,2})\/(\d{2}|\d{4})$/.exec(text);
  if (m) {
    let year = Number(m[3]);
    if (year < 100) year += 2000;
    return new Date(Date.UTC(year, Number(m[1]) - 1, Number(m[2])));
  }
  // "Aug 14 2026" / "August 14 2026" / "Aug 14 26"
  m = /^([A-Za-z]+)\s+(\d{1,2})\s+(\d{2}|\d{4})$/.exec(text);
  if (m) {
    const month = MONTHS[m[1].toLowerCase()];
    if (month) {
      let year = Number(m[3]);
      if (year < 100) year += 2000;
      return new Date(Date.UTC(year, month - 1, Number(m[2])));
    }
  }
  return null;
}

/** Best-effort to ISO (YYYY-MM-DD). Returns original if unparseable. */
export function toIso(value: string): string {
  const parsed = parseDate(value);
  if (!parsed || Number.isNaN(parsed.getTime())) return value;
  return `${parsed.getUTCFullYear()}-${pad(parsed.getUTCMonth() + 1)}-${pad(parsed.getUTCDate())}`;
}
