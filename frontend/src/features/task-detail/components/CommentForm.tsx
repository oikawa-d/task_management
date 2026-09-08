import { useState } from "react";

import { getConfiguredCommentBodyMaxLength, isPromiseLike } from "./formConfig";

export interface CommentFormProps {
	onSubmit: (body: string) => void | Promise<void>;
	isSubmitting?: boolean;
	error?: string;
	maxBodyLength?: number;
}

export function CommentForm({
	onSubmit,
	isSubmitting = false,
	error,
	maxBodyLength,
}: CommentFormProps) {
	const effectiveMaxBodyLength = maxBodyLength ?? getConfiguredCommentBodyMaxLength();
	const [body, setBody] = useState("");
	const [validationError, setValidationError] = useState<string>();
	const hasText = body.trim().length > 0;
	const isTooLong = body.length > effectiveMaxBodyLength;
	const isValid = hasText && !isTooLong;

	const submit = () => {
		if (!isValid) {
			setValidationError(
				!isTooLong
					? "コメントを入力してください"
					: `コメントは1〜${effectiveMaxBodyLength}文字で入力してください`,
			);
			return;
		}
		setValidationError(undefined);
		const result = onSubmit(body);
		if (isPromiseLike(result)) {
			void result.then(() => setBody(""), () => undefined);
		} else {
			setBody("");
		}
	};

	return (
		<form
			aria-label="コメント投稿"
			onSubmit={(event) => {
				event.preventDefault();
				submit();
			}}
		>
			<label>
				コメント
				<textarea
					value={body}
					rows={3}
					onChange={(event) => {
						const nextBody = event.target.value;
						setBody(nextBody);
						setValidationError(
							nextBody.length > effectiveMaxBodyLength
								? `コメントは1〜${effectiveMaxBodyLength}文字で入力してください`
								: undefined,
						);
					}}
					aria-invalid={Boolean(validationError)}
				/>
			</label>
			{validationError && <p role="alert">{validationError}</p>}
			{error && <p role="alert">{error}</p>}
			<button type="submit" disabled={!isValid || isSubmitting}>
				{isSubmitting ? "投稿中..." : "投稿"}
			</button>
		</form>
	);
}
