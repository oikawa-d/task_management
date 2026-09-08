import axios from "axios";

/** 422バリデーションエラー時にのみ含まれるフィールド単位のエラー情報（basic_design/04_api.md §4.1）。 */
export interface ApiErrorDetail {
	field: string;
	message: string;
}

/** バックエンドの統一エラーレスポンス形式（basic_design/04_api.md §4.1）。 */
export interface ApiErrorBody {
	code: string;
	message: string;
	details: ApiErrorDetail[] | null;
	request_id: string | null;
}

const UNKNOWN_ERROR_CODE = "UNKNOWN_ERROR";
const NETWORK_ERROR_CODE = "NETWORK_ERROR";
const UNKNOWN_ERROR_MESSAGE = "予期しないエラーが発生しました";

interface ApiErrorParams {
	code: string;
	message: string;
	status: number | null;
	details?: ApiErrorDetail[] | null;
	requestId?: string | null;
}

/** フロントエンド全体で共通して扱うエラー型。axiosエラー・ネットワークエラー・想定外の例外をすべてこの形式へ正規化する。 */
export class ApiError extends Error {
	readonly code: string;
	readonly status: number | null;
	readonly details: ApiErrorDetail[] | null;
	readonly requestId: string | null;

	constructor(params: ApiErrorParams) {
		super(params.message);
		this.name = "ApiError";
		this.code = params.code;
		this.status = params.status;
		this.details = params.details ?? null;
		this.requestId = params.requestId ?? null;
	}
}

function isApiErrorResponseBody(data: unknown): data is { error: ApiErrorBody } {
	if (typeof data !== "object" || data === null || !("error" in data)) {
		return false;
	}

	const { error } = data as { error: unknown };
	return (
		typeof error === "object" &&
		error !== null &&
		"code" in error &&
		"message" in error
	);
}

/** axiosが投げるエラー・その他の例外を、アプリ共通の {@link ApiError} 形式へ変換する。 */
export function toApiError(error: unknown): ApiError {
	if (error instanceof ApiError) {
		return error;
	}

	if (axios.isAxiosError(error)) {
		const responseData: unknown = error.response?.data;

		if (isApiErrorResponseBody(responseData)) {
			const body = responseData.error;
			return new ApiError({
				code: body.code,
				message: body.message,
				status: error.response?.status ?? null,
				details: body.details,
				requestId: body.request_id,
			});
		}

		if (error.response) {
			return new ApiError({
				code: UNKNOWN_ERROR_CODE,
				message: error.message,
				status: error.response.status,
			});
		}

		return new ApiError({
			code: NETWORK_ERROR_CODE,
			message: error.message,
			status: null,
		});
	}

	if (error instanceof Error) {
		return new ApiError({ code: UNKNOWN_ERROR_CODE, message: error.message, status: null });
	}

	return new ApiError({ code: UNKNOWN_ERROR_CODE, message: UNKNOWN_ERROR_MESSAGE, status: null });
}
