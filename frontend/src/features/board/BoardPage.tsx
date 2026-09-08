import { useParams } from "react-router-dom";

import type { BoardResponse, TaskStatus } from "./types";

const COLUMN_LABELS: Record<TaskStatus, string> = {
	todo: "未着手",
	in_progress: "進行中",
	done: "完了",
};

const EMPTY_BOARD: BoardResponse = {
	columns: { todo: [], in_progress: [], done: [] },
};

export interface BoardPageProps {
	board?: BoardResponse | null;
	errorStatus?: number;
	isLoading?: boolean;
}

export function BoardPage({ board = EMPTY_BOARD, errorStatus, isLoading = false }: BoardPageProps) {
	const { projectId } = useParams();

	if (errorStatus === 404 || !projectId) {
		return <p role="alert">プロジェクトが見つかりません</p>;
	}

	if (isLoading || !board) {
		return <p role="status">ボードを読み込み中...</p>;
	}

	return (
		<main>
			<h1>プロジェクト {projectId}</h1>
			<div className="board-columns">
				{(Object.keys(COLUMN_LABELS) as TaskStatus[]).map((status) => (
					<section key={status} aria-label={COLUMN_LABELS[status]}>
						<h2>{COLUMN_LABELS[status]} ({board.columns[status].length})</h2>
						<ul>
							{board.columns[status].map((task) => (
								<li key={task.id} data-task-id={task.id}>{task.title}</li>
							))}
						</ul>
					</section>
				))}
			</div>
		</main>
	);
}
