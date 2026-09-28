import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ROUTES } from "../../routes";
import { KanbanBoard } from "./components/KanbanBoard";
import { useBoard } from "./hooks/useBoard";
import { useUpdateTaskMutation } from "./hooks/useUpdateTaskMutation";
import { TaskDetailModal } from "./components/TaskDetailModal";
import { taskDetailStore } from "../../stores/taskDetailStore";
import styles from "./BoardPage.module.css";

export function BoardPage() {
	const { projectId, taskId } = useParams();
	const navigate = useNavigate();
	const { board, isLoading, error, refetch } = useBoard(projectId);
	const boardRefreshToken = useSyncExternalStore(
		taskDetailStore.subscribe,
		() => taskDetailStore.getSnapshot().boardRefreshToken,
		() => taskDetailStore.getSnapshot().boardRefreshToken,
	);
	const previousRefreshToken = useRef(boardRefreshToken);
	useEffect(() => {
		if (previousRefreshToken.current === boardRefreshToken) return;
		previousRefreshToken.current = boardRefreshToken;
		void refetch();
	}, [boardRefreshToken, refetch]);
	const [mutationMessage, setMutationMessage] = useState<string | null>(null);
	const updateTaskMutation = useUpdateTaskMutation(
		projectId ?? "",
		() => setMutationMessage("他のユーザーが更新したため最新の状態を表示しました。"),
		() => setMutationMessage("タスクの移動に失敗しました。元の状態へ戻しました。"),
	);
	if (!projectId) return <p className={styles.state}>プロジェクトが見つかりません</p>;
	return (
		<section className={styles.page}>
			<header className={styles.header}><h1>プロジェクト</h1></header>
			{isLoading && <p className={styles.state} role="status">ボードを読み込み中...</p>}
			<div className={styles.board}><KanbanBoard
				columns={board.columns}
				onTaskMove={(move) => {
					setMutationMessage(null);
					updateTaskMutation.mutate(move);
				}}
				onCardClick={(id) => navigate(ROUTES.TASK(projectId, id))}
				errorMessage={mutationMessage ?? (error ? "ボードを読み込めませんでした。" : null)}
			/></div>
			{taskId && <TaskDetailModal projectId={projectId} taskId={taskId} onClose={() => navigate(ROUTES.PROJECT(projectId))} />}
		</section>
	);
}
