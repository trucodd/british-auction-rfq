// Backend uses naive UTC datetimes. Treat them as UTC on display.
export function parseUtc(s: string): Date {
  return new Date(s.endsWith("Z") ? s : s + "Z");
}

// Pin the format so display is consistent regardless of viewer's environment.
// "en-GB" gives dd-mm-yyyy ordering, matching how the datetime-local inputs render.
const FMT = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: true,
});

export function fmtUtc(s: string | null | undefined): string {
  if (!s) return "—";
  return FMT.format(parseUtc(s));
}

// Convert <input type="datetime-local"> local value to naive UTC ISO for the API.
export function localInputToUtcIso(local: string): string {
  const d = new Date(local);
  return d.toISOString().slice(0, 19); // "YYYY-MM-DDTHH:MM:SS"
}