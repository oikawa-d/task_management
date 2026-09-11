export const FONT_SCALE_OPTIONS = [
	{ value: 0.875, label: "小" },
	{ value: 1, label: "標準" },
	{ value: 1.125, label: "大" },
	{ value: 1.25, label: "特大" },
] as const;

export type FontScale = (typeof FONT_SCALE_OPTIONS)[number]["value"];
