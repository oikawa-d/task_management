import { useUiStore } from "../../../stores/uiStore";
import { THEME_OPTIONS } from "../config/displayConfig";
import styles from "./ThemeSelector.module.css";

export function ThemeSelector() {
	const theme = useUiStore((state) => state.theme);
	const setTheme = useUiStore((state) => state.setTheme);
	return <label className={styles.field}>テーマ<select value={theme} onChange={(event) => setTheme(event.target.value as typeof theme)}>{THEME_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>;
}
