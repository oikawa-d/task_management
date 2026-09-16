import { useEffect, useRef, useState } from "react";

export interface UseHashTokenResult {
	token: string | null;
	ready: boolean;
}

function extractTokenFromHash(hash: string): string | null {
	const raw = hash.startsWith("#") ? hash.slice(1) : hash;
	if (!raw) {
		return null;
	}
	return new URLSearchParams(raw).get("token");
}

/**
 * URL fragment（`#token=...`）からトークンを取り出し、`history.replaceState` で
 * 直ちにURLから除去する。fragmentはブラウザからサーバーへ送信されないが、
 * ブラウザ履歴・画面遷移後のURLバー表示には残るため、抽出後は速やかに消去する。
 *
 * `useRef` による同期フラグでStrictModeの二重effect実行時も抽出・除去処理が
 * 1回しか走らないようにする。
 */
export function useHashToken(): UseHashTokenResult {
	const extractedRef = useRef(false);
	const [token, setToken] = useState<string | null>(null);
	const [ready, setReady] = useState(false);

	useEffect(() => {
		if (extractedRef.current) {
			return;
		}
		extractedRef.current = true;

		const extractedToken = extractTokenFromHash(window.location.hash);
		if (extractedToken) {
			window.history.replaceState(null, "", window.location.pathname + window.location.search);
		}
		setToken(extractedToken);
		setReady(true);
	}, []);

	return { token, ready };
}
