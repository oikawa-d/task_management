export const BREAKPOINTS = {
	sm: "30rem",
	md: "48rem",
	lg: "90rem",
} as const;

export type Breakpoint = (typeof BREAKPOINTS)[keyof typeof BREAKPOINTS];
