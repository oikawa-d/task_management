import type { Theme } from "../features/settings/config/displayConfig";

type ThemeWindow = Window & { __cerberusThemeCleanup?: () => void };

export function applyTheme(theme: Theme): void {
	if (typeof document === "undefined") return;
	if (theme === "system") document.documentElement.removeAttribute("data-theme");
	else document.documentElement.setAttribute("data-theme", theme);
}

export function subscribeSystemTheme(theme: Theme): void {
	if (typeof window === "undefined" || !window.matchMedia) return;
	const target = window as ThemeWindow;
	target.__cerberusThemeCleanup?.();
	delete target.__cerberusThemeCleanup;
	if (theme !== "system") return;
	const media = window.matchMedia("(prefers-color-scheme: dark)");
	const handleChange = () => applyTheme("system");
	if (media.addEventListener) media.addEventListener("change", handleChange);
	else media.addListener?.(handleChange);
	target.__cerberusThemeCleanup = () => {
		if (media.removeEventListener) media.removeEventListener("change", handleChange);
		else media.removeListener?.(handleChange);
	};
}
