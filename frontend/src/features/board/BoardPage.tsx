import { useNavigate, useParams } from "react-router-dom";

import { ROUTES } from "../../routes";
import { useBoard } from "./hooks/useBoard";
import { TaskCard } from "./components/TaskCard";
import { TaskDetailModal } from "./components/TaskDetailModal";
import type { TaskStatus } from "./types";

const COLUMN_LABELS: Record<TaskStatus, string> = { todo: "未着手", in_progress: "進行中", done: "完了" };

export function BoardPage() {
	const { projectId, taskId } = useParams();
	const navigate = useNavigate();
	const { board, isLoading, error } = useBoard(projectId);
	if (!projectId) return <p>プロジェクトが見つかりません</p>;
	const task = taskId
		? Object.values(board.columns).flat().find((boardTask) => boardTask.id === taskId)
		: undefined;

	return (
		<main>
			<h1>プロジェクト</h1>
			{isLoading && <p role="status">ボードを読み込み中...</p>}
			{error && <p role="alert">ボードを読み込めませんでした。</p>}
			<div className="board-columns">
				{(Object.keys(COLUMN_LABELS) as TaskStatus[]).map((status) => (
					<section key={status} aria-labelledby={`column-${status}`}>
						<h2 id={`column-${status}`}>{COLUMN_LABELS[status]} ({board.columns[status].length})</h2>
						<div>
							{board.columns[status].map((task) => <TaskCard key={task.id} task={task} onClick={(id) => navigate(ROUTES.TASK(projectId, id))} />)}
						</div>
					</section>
				))}
			</div>
			{taskId && <TaskDetailModal projectId={projectId} taskId={taskId} task={task} isLoading={isLoading} onClose={() => navigate(ROUTES.PROJECT(projectId))} />}
		</main>
	);
}
