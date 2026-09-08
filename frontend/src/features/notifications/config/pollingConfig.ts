/**
 * 未読通知件数ポーリングの設定値。
 * 間隔はハードコードせず環境変数 `VITE_NOTIFICATION_POLL_INTERVAL_MS` から取得する。
 * 参照: docs/basic_design/05_frontend.md §3.1, §6.2
 */

const DEFAULT_POLL_INTERVAL_MS = 60000;

/**
 * `VITE_NOTIFICATION_POLL_INTERVAL_MS` を解決する。
 * 未設定・不正値（数値でない、0以下）の場合は既定値にフォールバックする。
 */
export function getNotificationPollIntervalMs(
	env: ImportMetaEnv = import.meta.env,
): number {
	const raw = env.VITE_NOTIFICATION_POLL_INTERVAL_MS;
	const parsed = Number(raw);

	if (raw === undefined || raw === "" || !Number.isFinite(parsed) || parsed <= 0) {
		return DEFAULT_POLL_INTERVAL_MS;
	}

	return parsed;
}
