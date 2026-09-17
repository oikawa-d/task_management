import { useLoginHistory } from "../hooks/useLoginHistory";
import styles from "./LoginHistoryTable.module.css";

function formatDate(value: string): string {
	return new Date(value).toLocaleString("ja-JP");
}

export function LoginHistoryTable() {
	const query = useLoginHistory(true);
	if (query.isLoading) return <p className={styles.state} role="status">ログイン履歴を読み込み中...</p>;
	if (query.isError) return <div className={styles.state} role="alert">ログイン履歴を読み込めませんでした。<button type="button" onClick={() => void query.refetch()}>再試行</button></div>;
	if (!query.data?.items.length) return <p className={styles.state} role="status">ログイン履歴はありません。</p>;
	return (
		<div className={styles.wrapper}>
			<table className={styles.table}>
				<thead><tr><th>日時</th><th>方式</th><th>IPアドレス</th><th>結果</th></tr></thead>
				<tbody>{query.data.items.map((item) => <tr key={item.id}><td>{formatDate(item.created_at)}</td><td>{item.login_method}</td><td>{item.ip_address ?? "-"}</td><td>{item.success ? "成功" : "失敗"}</td></tr>)}</tbody>
			</table>
			<p>全{query.data.meta.count}件</p>
		</div>
	);
}
