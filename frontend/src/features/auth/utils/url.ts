/**
 * design doc: docs/detailed_design/screen/11_oauth_callback.md §9.3 isSafeRelativePath
 *
 * sessionモードでfragmentから取得した redirect_to を再検証する。
 * jwtモードはサーバーが正規化済みの値をレスポンスで返すため、この関数は使用しない。
 */
export function isSafeRelativePath(path: string | null | undefined): path is string {
	if (!path) {
		return false;
	}

	// "//evil.com"（プロトコル相対URL）や先頭が"\"の表記を拒否する
	if (path[0] !== "/" || path[1] === "/" || path[1] === "\\") {
		return false;
	}

	// "javascript:alert(1)" のようなスキーム注入を拒否する
	if (path.includes(":")) {
		return false;
	}

	return true;
}
