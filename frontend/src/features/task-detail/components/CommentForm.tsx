import { useState } from "react";

export interface CommentFormProps {
	onSubmit: (body: string) => void | Promise<void>;
	isSubmitting?: boolean;
	error?: string;
	maxBodyLength?: number;
}

function isPromiseLike(value: void | Promise<void>): value is Promise<void> {
	return typeof value === "object" && value !== null && "then" in value;
}

function getConfiguredMaxBodyLength(): number | undefined {
	const value = Number(import.meta.env.VITE_TASK_COMMENT_BODY_MAX_LENGTH);
	return Number.isInteger(value) && value > 0 ? value : undefined;
}

export function CommentForm({
	onSubmit,
	isSubmitting = false,
	error,
	maxBodyLength,
}: CommentFormProps) {
	const effectiveMaxBodyLength = maxBodyLength ?? getConfiguredMaxBodyLength();
	const [body, setBody] = useState("");
	const [validationError, setValidationError] = useState<string>();
	const hasText = body.trim().length > 0;
	const isTooLong = effectiveMaxBodyLength !== undefined && body.length > effectiveMaxBodyLength;
	const isValid = hasText && !isTooLong;

	const submit = () => {
		if (!isValid) {
			setValidationError(
				effectiveMaxBodyLength === undefined || !isTooLong
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
							effectiveMaxBodyLength !== undefined && nextBody.length > effectiveMaxBodyLength
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
