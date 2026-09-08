import { useNavigate, useParams } from "react-router-dom";

import { ROUTES } from "../../routes";
import { KanbanBoard } from "./components/KanbanBoard";
import { useBoard } from "./hooks/useBoard";
import { TaskDetailModal } from "./components/TaskDetailModal";

export function BoardPage() {
	const { projectId, taskId } = useParams();
	const navigate = useNavigate();
	const { board, isLoading, error } = useBoard(projectId);
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
				onCardClick={(id) => navigate(ROUTES.TASK(projectId, id))}
				errorMessage={error ? "ボードを読み込めませんでした。" : null}
			/>
			{taskId && <TaskDetailModal projectId={projectId} taskId={taskId} task={task} isLoading={isLoading} onClose={() => navigate(ROUTES.PROJECT(projectId))} />}
		</section>
	);
}
