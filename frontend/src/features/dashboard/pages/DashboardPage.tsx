import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ProjectCreateForm } from "../components/ProjectCreateForm";
import { ProjectList } from "../components/ProjectList";
import { Calendar } from "../components/Calendar";
import type { ProjectSummary } from "../api/types";
import { useDashboard } from "../hooks/useDashboard";
import { ROUTES } from "../../../routes";

function formatLocalDate(value: Date): string {
	return [value.getFullYear(), value.getMonth() + 1, value.getDate()]
		.map((part) => String(part).padStart(2, "0"))
		.join("-");
}

/**
 * docs/detailed_design/screen/06_dashboard.md
 * プロジェクト一覧はGET /api/projects、作成はPOST /api/projectsへ接続し、
 * 一覧・作成・カレンダーの取得stateとprojectStoreの選択IDはuseDashboardへ集約し、
 * 403は§11に従い個別メッセージを表示する。
 */
export function DashboardPage() {
	const navigate = useNavigate();
	const [isCreateOpen, setCreateOpen] = useState(false);
	const [calendarMonth, setCalendarMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
	const calendarRange = useMemo(() => {
		const first = new Date(calendarMonth.getFullYear(), calendarMonth.getMonth(), 1);
		const from = new Date(first);
		from.setDate(first.getDate() - first.getDay());
		const to = new Date(from);
		to.setDate(from.getDate() + 41);
		return { from: formatLocalDate(from), to: formatLocalDate(to) };
	}, [calendarMonth]);
	const { projectsQuery, createProjectMutation, calendarQuery, selectedProjectId, selectProject } = useDashboard({
		calendarParams: { ...calendarRange, scope: "me" },
	});

	const handleCreate = async (payload: Parameters<typeof createProjectMutation.mutateAsync>[0]) => {
		await createProjectMutation.mutateAsync(payload);
		setCreateOpen(false);
	};

	const handleSelect = (project: ProjectSummary) => {
		selectProject(project.id);
		navigate(ROUTES.PROJECT(project.id));
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
					isLoading={projectsQuery.isLoading}
					isError={projectsQuery.isError}
					error={projectsQuery.error}
					projects={projectsQuery.data?.items}
					selectedProjectId={selectedProjectId}
					onSelect={handleSelect}
					onRetry={() => void projectsQuery.refetch()}
					onCreateClick={() => setCreateOpen(true)}
				/>
			</section>
			<section aria-labelledby="calendar-heading">
				<h2 id="calendar-heading">期限カレンダー</h2>
				<Calendar
					month={calendarMonth}
					tasks={calendarQuery.data ?? []}
					isLoading={calendarQuery.isLoading}
					isError={calendarQuery.isError}
					onRetry={() => void calendarQuery.refetch()}
					onPreviousMonth={() => setCalendarMonth((current) => new Date(current.getFullYear(), current.getMonth() - 1, 1))}
					onNextMonth={() => setCalendarMonth((current) => new Date(current.getFullYear(), current.getMonth() + 1, 1))}
				/>
			</section>
		</section>
	);
}
