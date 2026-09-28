import { useUiStore } from "../../../stores/uiStore";
import { THEME_OPTIONS } from "../config/displayConfig";
import styles from "./ThemeSelector.module.css";

/**
 * 現在のテーマを選択する設定UIを描画する。
 * @returns テーマ選択labelとselect要素のReact要素。
 * @副作用 選択変更時にuiStore.setThemeを呼び出し、テーマを永続化する。
 * @throws テーマstoreが利用できない場合はReactの描画エラーを送出する。
 */
export function ThemeSelector() {
	const theme = useUiStore((state) => state.theme);
	const setTheme = useUiStore((state) => state.setTheme);
	return <label className={styles.field}>テーマ<select value={theme} onChange={(event) => setTheme(event.target.value as typeof theme)}>{THEME_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>;
}
