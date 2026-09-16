import { AxiosError, type AxiosHeaders } from "axios";
import { describe, expect, it } from "vitest";

import { ApiError, toApiError } from "./errors";

function createAxiosError(status: number, data: unknown, headers: Record<string, string> = {}): AxiosError {
	return new AxiosError(
		`Request failed with status code ${status}`,
		"ERR_BAD_REQUEST",
		undefined,
		undefined,
		{
			data,
			status,
			statusText: "",
			headers: headers as AxiosHeaders,
			config: {} as never,
		},
	);
}

describe("toApiError", () => {
	it.each([
		[401, "TOKEN_EXPIRED"],
		[403, "CSRF_INVALID"],
		[409, "TASK_CONFLICT"],
		[422, "VALIDATION_ERROR"],
		[500, "INTERNAL_ERROR"],
		[503, "SERVICE_UNAVAILABLE"],
	])("HTTP %iのAPIエラーコードを保持する", (status, code) => {
		const result = toApiError(
			createAxiosError(status, {
				error: { code, message: "契約メッセージ", details: null, request_id: "req-1" },
			}),
		);

		expect(result).toMatchObject({ code, status, message: "契約メッセージ", requestId: "req-1" });
	});

	it("422のフィールド詳細と403のオブジェクト詳細を保持する", () => {
		const validation = toApiError(
			createAxiosError(422, {
				error: {
					code: "VALIDATION_ERROR",
					message: "入力内容に誤りがあります",
					details: [{ field: "password", message: "不正です" }],
					request_id: null,
				},
			}),
		);
		const forbidden = toApiError(
			createAxiosError(403, {
				error: { code: "FORBIDDEN", message: "権限がありません", details: { reason: "role" } },
			}),
		);

		expect(validation.details).toEqual([{ field: "password", message: "不正です" }]);
		expect(forbidden.details).toEqual({ reason: "role" });
	});

	it("契約外のHTTPエラーもステータスを保持した共通コードへ変換する", () => {
		expect(toApiError(createAxiosError(422, "invalid"))).toMatchObject({
			code: "UNKNOWN_ERROR",
			status: 422,
		});
		expect(toApiError(createAxiosError(503, "unavailable"))).toMatchObject({
			code: "UNKNOWN_ERROR",
			status: 503,
		});
	});

	it("レスポンスが無い場合はネットワークエラーにする", () => {
		const result = toApiError(new AxiosError("Network Error", "ERR_NETWORK"));

		expect(result).toMatchObject({ code: "NETWORK_ERROR", status: null, message: "Network Error" });
	});

	it("request_idがbodyにない場合はレスポンスヘッダを使う", () => {
		const result = toApiError(
			createAxiosError(500, { error: { code: "INTERNAL_ERROR", message: "失敗", details: null } }, { "x-request-id": "header-1" }),
		);

		expect(result.requestId).toBe("header-1");
	});

	it("ApiErrorと想定外の例外を共通型へ変換する", () => {
		const original = new ApiError({ code: "CUSTOM", message: "custom", status: null });

		expect(toApiError(original)).toBe(original);
		expect(toApiError(new Error("unexpected"))).toMatchObject({ code: "UNKNOWN_ERROR", message: "unexpected" });
	});
});
