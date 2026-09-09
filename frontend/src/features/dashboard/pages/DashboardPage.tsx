import { useState } from "react";
import { useNavigate } from "react-router-dom";

type Project = { id: string; name: string };

export function DashboardPage() {
	const navigate = useNavigate();
	const [projects, setProjects] = useState<Project[]>([]);
	const [isCreateOpen, setCreateOpen] = useState(false);
	const [name, setName] = useState("");

	const createProject = () => {
		const projectName = name.trim();
		if (!projectName) return;
		setProjects((current) => [...current, { id: crypto.randomUUID(), name: projectName }]);
		setName("");
		setCreateOpen(false);
	};

	return (
		<section>
			<header>
				<h1>ダッシュボード</h1>
				<button type="button" onClick={() => setCreateOpen(true)}>プロジェクトを作成</button>
			</header>
			{isCreateOpen && (
				<form onSubmit={(event) => { event.preventDefault(); createProject(); }}>
					<label htmlFor="project-name">プロジェクト名</label>
					<input id="project-name" value={name} onChange={(event) => setName(event.target.value)} />
					<button type="submit">作成</button>
					<button type="button" onClick={() => setCreateOpen(false)}>キャンセル</button>
				</form>
			)}
			<section aria-labelledby="project-list-heading">
				<h2 id="project-list-heading">プロジェクト一覧</h2>
				{projects.length === 0 ? <p>プロジェクトがありません。</p> : (
					<ul>{projects.map((project) => <li key={project.id}><button type="button" onClick={() => navigate(`/projects/${project.id}`)}>{project.name}</button></li>)}</ul>
				)}
			</section>
			<section aria-labelledby="calendar-heading">
				<h2 id="calendar-heading">期限カレンダー</h2>
				<p>期限のあるタスクをここに表示します。</p>
			</section>
		</section>
	);
}
