import { useState } from "react";

import { getConfiguredCommentBodyMaxLength, isPromiseLike } from "../formConfig";
import styles from "./CommentList.module.css";

export interface CommentAuthor {
	id: string;
	username: string;
	display_name: string;
}

export interface TaskComment {
	id: string;
	task_id: string;
	body: string;
	author: CommentAuthor;
	created_at: string;
	updated_at: string;
}

export interface CommentListProps {
	comments: TaskComment[];
	currentUserId: string;
	currentUserRole: "member" | "admin";
	onEdit?: (commentId: string, body: string) => void | Promise<void>;
	onDelete?: (commentId: string) => void | Promise<void>;
	error?: string;
	maxBodyLength?: number;
}

export function CommentList({
	comments,
	currentUserId,
	currentUserRole,
	onEdit,
	onDelete,
	error,
	maxBodyLength,
}: CommentListProps) {
	const effectiveMaxBodyLength = maxBodyLength ?? getConfiguredCommentBodyMaxLength();
	const [editingCommentId, setEditingCommentId] = useState<string | null>(null);
	const [draft, setDraft] = useState("");
	const [validationError, setValidationError] = useState<string>();
	const sortedComments = comments.slice().sort((left, right) => left.created_at.localeCompare(right.created_at));

	const startEditing = (comment: TaskComment) => {
		setEditingCommentId(comment.id);
		setDraft(comment.body);
		setValidationError(undefined);
	};

	const save = () => {
		const trimmed = draft.trim();
		if (!trimmed) {
			setValidationError("コメントを入力してください");
			return;
		}
		if (trimmed.length > effectiveMaxBodyLength) {
			setValidationError(`コメントは1〜${effectiveMaxBodyLength}文字で入力してください`);
			return;
		}
		setValidationError(undefined);
		const result = onEdit?.(editingCommentId ?? "", draft);
		if (isPromiseLike(result)) {
			void result.then(() => setEditingCommentId(null), () => undefined);
		} else {
			setEditingCommentId(null);
		}
	};

	const remove = (commentId: string) => {
		if (!window.confirm("このコメントを削除しますか？")) return;
		const result = onDelete?.(commentId);
		if (isPromiseLike(result)) void result.catch(() => undefined);
	};

	return (
		<section className={styles.listSection} aria-label="コメント一覧">
			{error && <p className={styles.error} role="alert">{error}</p>}
			{!error && sortedComments.length === 0 && <p className={styles.empty}>コメントはありません</p>}
			{sortedComments.length > 0 && (
					<ul className={styles.list}>
					{sortedComments.map((comment) => {
						const canModify =
							comment.author.id === currentUserId || currentUserRole === "admin";
						return (
							<li className={styles.item} key={comment.id} role="article">
								<div className={styles.meta}>
									<span>{comment.author.display_name}</span>
									<time dateTime={comment.created_at}>{comment.created_at}</time>
								</div>
								{editingCommentId === comment.id ? (
									<>
										<label className={styles.editor}>
											コメントを編集
											<textarea value={draft} onChange={(event) => setDraft(event.target.value)} />
										</label>
										{validationError && <p className={styles.error} role="alert">{validationError}</p>}
										<div className={styles.actions}><button type="button" onClick={save}>保存</button>
										<button type="button" onClick={() => setEditingCommentId(null)}>
											キャンセル
										</button>
										</div>
									</>
								) : (
									<p className={styles.body}>{comment.body}</p>
								)}
								{canModify && editingCommentId !== comment.id && (
									<div className={styles.actions}>
										<button type="button" onClick={() => startEditing(comment)}>
											編集
										</button>
										<button type="button" onClick={() => remove(comment.id)}>
											削除
										</button>
									</div>
								)}
							</li>
						);
					})}
				</ul>
			)}
		</section>
	);
}
