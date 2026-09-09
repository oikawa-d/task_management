/** onSubmit/onEdit等のコールバックがPromiseを返したかどうかを判定する */
export function isPromiseLike(value: void | Promise<void>): value is Promise<void> {
	return typeof value === "object" && value !== null && "then" in value;
}

const COMMENT_BODY_MAX_LENGTH_DEFAULT = 2000;

function parseMaxLengthEnv(rawValue: string | undefined, fallback: number): number {
	const value = Number(rawValue);
	return Number.isInteger(value) && value > 0 ? value : fallback;
}

/** コメント本文の上限文字数。`VITE_TASK_COMMENT_BODY_MAX_LENGTH`未設定・不正値の場合は既定値2000を用いる */
export function getConfiguredCommentBodyMaxLength(): number {
	return parseMaxLengthEnv(import.meta.env.VITE_TASK_COMMENT_BODY_MAX_LENGTH, COMMENT_BODY_MAX_LENGTH_DEFAULT);
}
