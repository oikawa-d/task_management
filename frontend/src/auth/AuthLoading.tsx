import styles from "./AuthLoading.module.css";

export function AuthLoading() {
	return <div className={styles.loading} role="status" aria-label="認証状態を確認中..."><span className={styles.spinner} aria-hidden="true" />認証状態を確認中...</div>;
}
