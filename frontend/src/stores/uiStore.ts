import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { FontScale } from "../features/settings/config/displayConfig";

interface UiState {
	fontScale: FontScale;
	setFontScale: (fontScale: FontScale) => void;
}

export const useUiStore = create<UiState>()(
	persist(
		(set) => ({
			fontScale: 1,
			setFontScale: (fontScale) => {
				if (typeof document !== "undefined") document.documentElement.style.setProperty("--font-scale", String(fontScale));
				set({ fontScale });
			},
		}),
		{
			name: "cerberus.ui",
			partialize: (state) => ({ fontScale: state.fontScale }),
			onRehydrateStorage: () => (state) => {
				if (state && typeof document !== "undefined") document.documentElement.style.setProperty("--font-scale", String(state.fontScale));
			},
		},
	),
);
