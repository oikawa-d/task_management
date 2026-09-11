import type { AdminProject } from "../api/adminApi";

export function ProjectTable({ items, onDelete }: { items: AdminProject[]; onDelete: (project: AdminProject) => void }) { return <table><thead><tr><th>プロジェクト</th><th>オーナー</th><th>メンバー数</th><th>状態</th><th>操作</th></tr></thead><tbody>{items.map((project) => <tr key={project.id}><td>{project.name}</td><td>{project.owner.display_name}</td><td>{project.member_count}</td><td>{project.is_active ? "有効" : "無効"}</td><td><button type="button" disabled={!project.is_active} onClick={() => onDelete(project)}>無効化</button></td></tr>)}</tbody></table>; }
