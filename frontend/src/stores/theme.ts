import type { Theme } from "../features/settings/config/displayConfig";

type ThemeWindow = Window & { __cerberusThemeCleanup?: () => void };

/**
 * 選択されたテーマをdocument要素へ反映する。
 * @param theme 明示テーマまたはOS追従を表すテーマ値。
 * @returns なし。
 * @副作用 明示テーマではdata-theme属性を設定し、systemでは削除する。
 * @throws ブラウザDOMが存在しない環境では何もせず、例外を送出しない。
 */
export function applyTheme(theme: Theme): void {
	if (typeof document === "undefined") return;
	if (theme === "system") document.documentElement.removeAttribute("data-theme");
	else document.documentElement.setAttribute("data-theme", theme);
}

/**
 * systemテーマ選択時のmatchMedia監視を登録し、既存監視を解除する。
 * @param theme 監視対象を決めるテーマ値。
 * @returns なし。
 * @副作用 matchMediaのchange listenerを登録または解除する。
 * @throws ブラウザのwindowまたはmatchMediaがない環境では何もせず、例外を送出しない。
 */
export function subscribeSystemTheme(theme: Theme): void {
	if (typeof window === "undefined" || !window.matchMedia) return;
	const target = window as ThemeWindow;
	target.__cerberusThemeCleanup?.();
	delete target.__cerberusThemeCleanup;
	if (theme !== "system") return;
	const media = window.matchMedia("(prefers-color-scheme: dark)");
	/**
	 * OSテーマ変更時にsystemテーマのDOM反映を再実行する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 documentのdata-theme属性を更新する。
	 * @throws DOMが存在しない場合は何もせず、例外を送出しない。
	 */
	const handleChange = () => applyTheme("system");
	if (media.addEventListener) media.addEventListener("change", handleChange);
	else media.addListener?.(handleChange);
	/**
	 * 登録したOSテーマ変更listenerを解除する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 MediaQueryListのlistener登録を解除する。
	 * @throws listener解除APIが存在しない場合も何もせず、例外を送出しない。
	 */
	target.__cerberusThemeCleanup = () => {
		if (media.removeEventListener) media.removeEventListener("change", handleChange);
		else media.removeListener?.(handleChange);
	};
}
