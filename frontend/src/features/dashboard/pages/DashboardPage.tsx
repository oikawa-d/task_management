import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ProjectCreateForm } from "../components/ProjectCreateForm";
import { ProjectList } from "../components/ProjectList";
import { useCreateProject } from "../hooks/useCreateProject";
import { useProjects } from "../hooks/useProjects";

/**
 * docs/detailed_design/screen/06_dashboard.md
 * プロジェクト一覧はGET /api/projects、作成はPOST /api/projectsへ接続し、
 * loading/error/empty/loadedの4状態と作成成功時の再取得をTanStack Queryで管理する。
 */
export function DashboardPage() {
	const navigate = useNavigate();
	const [isCreateOpen, setCreateOpen] = useState(false);
	const { data, isLoading, isError, refetch } = useProjects();
	const createProjectMutation = useCreateProject();

	const handleCreate = async (payload: Parameters<typeof createProjectMutation.mutateAsync>[0]) => {
		await createProjectMutation.mutateAsync(payload);
		setCreateOpen(false);
	};

	return (
		<section>
			<header>
				<h1>ダッシュボード</h1>
				<button type="button" onClick={() => setCreateOpen(true)}>
					プロジェクトを作成
				</button>
			</header>
			{isCreateOpen && <ProjectCreateForm onSubmit={handleCreate} onCancel={() => setCreateOpen(false)} />}
			<section aria-labelledby="project-list-heading">
				<h2 id="project-list-heading">プロジェクト一覧</h2>
				<ProjectList
					isLoading={isLoading}
					isError={isError}
					projects={data?.items}
					onSelect={(projectId) => navigate(`/projects/${projectId}`)}
					onRetry={() => void refetch()}
					onCreateClick={() => setCreateOpen(true)}
				/>
			</section>
			<section aria-labelledby="calendar-heading">
				<h2 id="calendar-heading">期限カレンダー</h2>
				<p>期限のあるタスクをここに表示します。</p>
			</section>
		</section>
	);
}
