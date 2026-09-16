const DEFAULT_APP_TIMEZONE = "Asia/Tokyo";

export const APP_TIMEZONE = import.meta.env.VITE_APP_TIMEZONE ?? DEFAULT_APP_TIMEZONE;

function partsToRecord(parts: Intl.DateTimeFormatPart[]): Record<string, string> {
	return Object.fromEntries(parts.filter(({ type }) => type !== "literal").map(({ type, value }) => [type, value]));
}

export function utcToLocalDateTime(value: string | null): string | null {
	if (!value) return null;
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return null;
	const parts = partsToRecord(new Intl.DateTimeFormat("en-CA", {
		timeZone: APP_TIMEZONE,
		year: "numeric",
		month: "2-digit",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
		hourCycle: "h23",
	}).formatToParts(date));
	return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

export function localDateTimeToUtc(value: string | null): string | null {
	if (!value) return null;
	const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
	if (!match) return null;
	const [year, month, day, hour, minute] = match.slice(1).map(Number);
	const localAsUtc = Date.UTC(year, month - 1, day, hour, minute);
	const zonedParts = partsToRecord(new Intl.DateTimeFormat("en-CA", {
		timeZone: APP_TIMEZONE,
		year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
	}).formatToParts(new Date(localAsUtc)));
	const zonedAsUtc = Date.UTC(
		Number(zonedParts.year), Number(zonedParts.month) - 1, Number(zonedParts.day),
		Number(zonedParts.hour), Number(zonedParts.minute),
	);
	return new Date(localAsUtc - (zonedAsUtc - localAsUtc)).toISOString();
}
