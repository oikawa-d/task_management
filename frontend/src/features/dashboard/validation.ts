import { z } from "zod";
import type { FieldErrors, FieldValues, Resolver } from "react-hook-form";

import { PROJECT_DESCRIPTION_MAX_LENGTH, PROJECT_NAME_MAX_LENGTH, PROJECT_NAME_MIN_LENGTH } from "./config/dashboardConfig";

/**
 * プロジェクト作成フォームのzodスキーマ。
 * docs/detailed_design/screen/06_dashboard.md §10（name 1〜100文字必須、description 0〜2000文字任意）
 */
export const projectCreateSchema = z.object({
	name: z
		.string()
		.min(PROJECT_NAME_MIN_LENGTH, "プロジェクト名を1〜100文字で入力してください")
		.max(PROJECT_NAME_MAX_LENGTH, "プロジェクト名を1〜100文字で入力してください"),
	description: z.string().max(PROJECT_DESCRIPTION_MAX_LENGTH, "説明は2000文字以内で入力してください"),
});

export type ProjectCreateFormValues = z.infer<typeof projectCreateSchema>;

/** frontend/src/features/auth/validation.ts の createZodResolver と同じ変換方針に揃える */
export function createZodResolver<T extends FieldValues>(schema: z.ZodType<T>): Resolver<T> {
	return async (values) => {
		const result = schema.safeParse(values);
		if (result.success) {
			return { values: result.data, errors: {} };
		}

		const errors: FieldErrors<T> = {};
		for (const issue of result.error.issues) {
			const field = issue.path[0];
			if (typeof field === "string" && !(field in errors)) {
				(errors as Record<string, unknown>)[field] = { type: issue.code, message: issue.message };
			}
		}
		return { values: {}, errors };
	};
}
