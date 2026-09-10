import type { ProjectSummary } from "../api/types";

export interface ProjectListProps {
	isLoading: boolean;
	isError: boolean;
	projects: ProjectSummary[] | undefined;
	onSelect: (projectId: string) => void;
	onRetry: () => void;
	onCreateClick: () => void;
}

/**
 * docs/detailed_design/screen/06_dashboard.md §6（Loading/Empty/Loaded/Error）、§11
 */
export function ProjectList({ isLoading, isError, projects, onSelect, onRetry, onCreateClick }: ProjectListProps) {
	if (isLoading) {
		return <p role="status">読み込み中です…</p>;
	}

	if (isError) {
		return (
			<div role="alert">
				<p>プロジェクト一覧の取得に失敗しました。</p>
				<button type="button" onClick={onRetry}>
					再試行
				</button>
			</div>
		);
	}

	const items = projects ?? [];

	if (items.length === 0) {
		return (
			<div role="status">
				<p>まだプロジェクトがありません。</p>
				<button type="button" onClick={onCreateClick}>
					作成する
				</button>
			</div>
		);
	}

	return (
		<ul>
			{items.map((project) => (
				<li key={project.id}>
					<button type="button" onClick={() => onSelect(project.id)}>
						{project.name}
					</button>
					{project.description && <p>{project.description}</p>}
					<span>メンバー {project.member_count}人</span>
					<span>
						todo {project.task_counts.todo} / in_progress {project.task_counts.in_progress} / done {project.task_counts.done}
					</span>
				</li>
			))}
		</ul>
	);
}
