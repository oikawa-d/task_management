import { AxiosError, type AxiosHeaders } from "axios";
import { describe, expect, it } from "vitest";

import { ApiError, toApiError } from "./errors";

function createAxiosError(params: {
	status?: number;
	data?: unknown;
	message?: string;
}): AxiosError {
	const { status, data, message = "Request failed" } = params;

	return new AxiosError(
		message,
		"ERR_BAD_REQUEST",
		undefined,
		undefined,
		status === undefined
			? undefined
			: {
					data,
					status,
					statusText: "",
					headers: {} as AxiosHeaders,
					config: {} as never,
				},
	);
}

describe("toApiError", () => {
	it("バックエンドの統一エラーフォーマットをApiErrorへ変換する", () => {
		const axiosError = createAxiosError({
			status: 403,
			data: {
				error: {
					code: "PROJECT_FORBIDDEN",
					message: "このプロジェクトへのアクセス権がありません",
					details: null,
					request_id: "req-1",
				},
			},
		});

		const result = toApiError(axiosError);

		expect(result).toBeInstanceOf(ApiError);
		expect(result).toMatchObject({
			code: "PROJECT_FORBIDDEN",
			message: "このプロジェクトへのアクセス権がありません",
			status: 403,
			details: null,
			requestId: "req-1",
		});
	});

	it("422バリデーションエラーのdetailsを保持する", () => {
		const axiosError = createAxiosError({
			status: 422,
			data: {
				error: {
					code: "VALIDATION_ERROR",
					message: "入力内容に誤りがあります",
					details: [{ field: "password", message: "8文字以上で入力してください" }],
					request_id: "req-2",
				},
			},
		});

		const result = toApiError(axiosError);

		expect(result.details).toEqual([{ field: "password", message: "8文字以上で入力してください" }]);
	});

	it("バックエンド形式でないレスポンスは未知エラーとして扱う", () => {
		const axiosError = createAxiosError({ status: 500, data: "Internal Server Error" });

		const result = toApiError(axiosError);

		expect(result.code).toBe("UNKNOWN_ERROR");
		expect(result.status).toBe(500);
	});

	it("レスポンスが無い場合はネットワークエラーとして扱う", () => {
		const axiosError = createAxiosError({ message: "Network Error" });

		const result = toApiError(axiosError);

		expect(result.code).toBe("NETWORK_ERROR");
		expect(result.status).toBeNull();
		expect(result.message).toBe("Network Error");
	});

	it("axios以外の例外はApiErrorへラップする", () => {
		const result = toApiError(new Error("unexpected"));

		expect(result).toBeInstanceOf(ApiError);
		expect(result.code).toBe("UNKNOWN_ERROR");
		expect(result.message).toBe("unexpected");
	});

	it("Errorインスタンスでない例外は既定メッセージへ変換する", () => {
		const result = toApiError("unexpected string throw");

		expect(result).toBeInstanceOf(ApiError);
		expect(result.code).toBe("UNKNOWN_ERROR");
		expect(result.message).toBe("予期しないエラーが発生しました");
	});

	it("ApiErrorはそのまま返す", () => {
		const original = new ApiError({ code: "X", message: "m", status: null });

		expect(toApiError(original)).toBe(original);
	});
});
