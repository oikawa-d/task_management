import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { FontScale, Theme } from "../features/settings/config/displayConfig";
import { applyTheme, subscribeSystemTheme } from "./theme";

interface UiState {
	fontScale: FontScale;
	theme: Theme;
	setFontScale: (fontScale: FontScale) => void;
	setTheme: (theme: Theme) => void;
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
				subscribeSystemTheme(theme);
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
				subscribeSystemTheme(state.theme);
			},
		},
	),
);
