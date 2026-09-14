import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ProjectCreateForm } from "../components/ProjectCreateForm";
import { ProjectList } from "../components/ProjectList";
import { Calendar } from "../components/Calendar";
import { useCreateProject } from "../hooks/useCreateProject";
import { useProjects } from "../hooks/useProjects";
import { useCalendarTasks } from "../hooks/useCalendarTasks";

function formatLocalDate(value: Date): string {
	return [value.getFullYear(), value.getMonth() + 1, value.getDate()]
		.map((part) => String(part).padStart(2, "0"))
		.join("-");
}

/**
 * docs/detailed_design/screen/06_dashboard.md
 * プロジェクト一覧はGET /api/projects、作成はPOST /api/projectsへ接続し、
 * loading/error/empty/loadedの4状態と作成成功時の再取得をTanStack Queryで管理する。
 */
export function DashboardPage() {
	const navigate = useNavigate();
	const [isCreateOpen, setCreateOpen] = useState(false);
	const [calendarMonth, setCalendarMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
	const { data, isLoading, isError, refetch } = useProjects();
	const createProjectMutation = useCreateProject();
	const calendarRange = useMemo(() => {
		const first = new Date(calendarMonth.getFullYear(), calendarMonth.getMonth(), 1);
		const from = new Date(first);
		from.setDate(first.getDate() - first.getDay());
		const to = new Date(from);
		to.setDate(from.getDate() + 41);
		return { from: formatLocalDate(from), to: formatLocalDate(to) };
	}, [calendarMonth]);
	const calendarQuery = useCalendarTasks({ ...calendarRange, scope: "me" });

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
