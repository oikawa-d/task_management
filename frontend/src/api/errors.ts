import axios, { type AxiosError } from "axios";

export interface ApiErrorDetail {
	field: string;
	message: string;
}

/** basic_design/04_api.md §4.1 のdetails。422以外ではオブジェクトも返り得る。 */
export type ApiErrorDetails = ApiErrorDetail[] | Record<string, unknown> | null;

export interface ApiErrorBody {
	code: string;
	message: string;
	details: ApiErrorDetails;
	request_id: string | null;
}

const UNKNOWN_ERROR_CODE = "UNKNOWN_ERROR";
const NETWORK_ERROR_CODE = "NETWORK_ERROR";
const UNKNOWN_ERROR_MESSAGE = "予期しないエラーが発生しました";

interface ApiErrorParams {
	code: string;
	message: string;
	status: number | null;
	details?: ApiErrorDetails;
	requestId?: string | null;
}

export class ApiError extends Error {
	readonly code: string;
	readonly status: number | null;
	readonly details: ApiErrorDetails;
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

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isDetails(value: unknown): value is ApiErrorDetails {
	if (value === null || value === undefined) {
		return true;
	}
	if (Array.isArray(value)) {
		return value.every((item) => isRecord(item) && typeof item.field === "string" && typeof item.message === "string");
	}
	return isRecord(value);
}

function isApiErrorResponseBody(data: unknown): data is { error: ApiErrorBody } {
	if (!isRecord(data) || !isRecord(data.error)) {
		return false;
	}
	const error = data.error;
	return (
		typeof error.code === "string" &&
		typeof error.message === "string" &&
		(error.request_id === undefined || error.request_id === null || typeof error.request_id === "string") &&
		isDetails(error.details)
	);
}

function getHeaderRequestId(error: AxiosError): string | null {
	const headers = error.response?.headers;
	if (!headers) {
		return null;
	}
	const headerValue = typeof headers.get === "function" ? headers.get("x-request-id") : headers["x-request-id"];
	return typeof headerValue === "string" ? headerValue : null;
}

/** AxiosError、ネットワークエラー、想定外例外を画面共通のApiErrorへ変換する。 */
export function toApiError(error: unknown): ApiError {
	if (error instanceof ApiError) {
		return error;
	}

	if (axios.isAxiosError(error)) {
		const response = error.response;
		if (response && isApiErrorResponseBody(response.data)) {
			const body = response.data.error;
			return new ApiError({
				code: body.code,
				message: body.message,
				status: response.status,
				details: body.details,
				requestId: body.request_id ?? getHeaderRequestId(error),
			});
		}

		return new ApiError({
			code: response ? UNKNOWN_ERROR_CODE : NETWORK_ERROR_CODE,
			message: error.message,
			status: response?.status ?? null,
			requestId: getHeaderRequestId(error),
		});
	}

	if (error instanceof Error) {
		return new ApiError({ code: UNKNOWN_ERROR_CODE, message: error.message, status: null });
	}

	return new ApiError({ code: UNKNOWN_ERROR_CODE, message: UNKNOWN_ERROR_MESSAGE, status: null });
}
