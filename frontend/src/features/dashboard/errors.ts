import { ApiError } from "../../api/errors";
import { FORBIDDEN_FALLBACK_MESSAGE, FORBIDDEN_MESSAGES, FORBIDDEN_STATUS } from "./config/dashboardConfig";

/** 403のときだけ、error codeに対応した画面表示メッセージを返す。403以外はnull。 */
export function resolveForbiddenMessage(error: unknown): string | null {
	if (!(error instanceof ApiError) || error.status !== FORBIDDEN_STATUS) {
		return null;
	}
	return FORBIDDEN_MESSAGES[error.code] ?? FORBIDDEN_FALLBACK_MESSAGE;
}
