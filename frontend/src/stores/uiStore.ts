import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { FontScale, Theme } from "../features/settings/config/displayConfig";

interface UiState {
	fontScale: FontScale;
	theme: Theme;
	setFontScale: (fontScale: FontScale) => void;
	setTheme: (theme: Theme) => void;
}

function applyTheme(theme: Theme) {
	if (typeof document === "undefined") return;
	if (theme === "system") {
		document.documentElement.removeAttribute("data-theme");
	} else {
		document.documentElement.setAttribute("data-theme", theme);
	}
}

function watchSystemTheme(theme: Theme) {
	if (typeof window === "undefined" || !window.matchMedia) return;
	const media = window.matchMedia("(prefers-color-scheme: dark)");
	const handler = () => {
		if (useUiStore.getState().theme === "system") applyTheme("system");
	};
	const target = window as Window & { __cerberusThemeCleanup?: () => void };
	target.__cerberusThemeCleanup?.();
	if (theme !== "system") return;
	media.addEventListener?.("change", handler);
	target.__cerberusThemeCleanup = () => media.removeEventListener?.("change", handler);
}

export const useUiStore = create<UiState>()(
	persist(
		(set) => ({
			fontScale: 1,
			theme: "system",
			setFontScale: (fontScale) => {
				if (typeof document !== "undefined") document.documentElement.style.setProperty("--font-scale", String(fontScale));
				set({ fontScale });
			},
			setTheme: (theme) => {
				applyTheme(theme);
				watchSystemTheme(theme);
				set({ theme });
			},
		}),
		{
			name: "cerberus.ui",
			partialize: (state) => ({ fontScale: state.fontScale, theme: state.theme }),
			onRehydrateStorage: () => (state) => {
				if (!state) return;
				if (typeof document !== "undefined") document.documentElement.style.setProperty("--font-scale", String(state.fontScale));
				applyTheme(state.theme);
				watchSystemTheme(state.theme);
			},
		},
	),
);
