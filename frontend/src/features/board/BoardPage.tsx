import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ROUTES } from "../../routes";
import { KanbanBoard } from "./components/KanbanBoard";
import { useBoard } from "./hooks/useBoard";
import { useUpdateTaskMutation } from "./hooks/useUpdateTaskMutation";
import { TaskDetailModal } from "./components/TaskDetailModal";

export function BoardPage() {
	const { projectId, taskId } = useParams();
	const navigate = useNavigate();
	const { board, isLoading, error } = useBoard(projectId);
	const [mutationMessage, setMutationMessage] = useState<string | null>(null);
	const updateTaskMutation = useUpdateTaskMutation(
		projectId ?? "",
		() => setMutationMessage("他のユーザーが更新したため最新の状態を表示しました。"),
		() => setMutationMessage("タスクの移動に失敗しました。元の状態へ戻しました。"),
	);
	if (!projectId) return <p>プロジェクトが見つかりません</p>;
	const task = taskId
		? Object.values(board.columns).flat().find((boardTask) => boardTask.id === taskId)
		: undefined;

	return (
		<section>
			<h1>プロジェクト</h1>
			{isLoading && <p role="status">ボードを読み込み中...</p>}
			<KanbanBoard
				columns={board.columns}
				onTaskMove={(move) => {
					setMutationMessage(null);
					updateTaskMutation.mutate(move);
				}}
				onCardClick={(id) => navigate(ROUTES.TASK(projectId, id))}
				errorMessage={mutationMessage ?? (error ? "ボードを読み込めませんでした。" : null)}
			/>
			{taskId && <TaskDetailModal projectId={projectId} taskId={taskId} task={task} isLoading={isLoading} onClose={() => navigate(ROUTES.PROJECT(projectId))} />}
		</section>
	);
}
