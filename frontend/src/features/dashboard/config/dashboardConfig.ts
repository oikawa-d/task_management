/**
 * ダッシュボードのプロジェクト一覧・作成フォームで使う既定値。
 * docs/detailed_design/api/projects/01_get_projects.md §2.1（page/per_page既定値）
 * docs/detailed_design/api/projects/02_post_projects.md §2.1（name制約）
 * docs/detailed_design/screen/06_dashboard.md §10（description制約、issue #40で確定）
 */
export const PROJECT_LIST_DEFAULT_PAGE = 1;
export const PROJECT_LIST_DEFAULT_PER_PAGE = 20;

export const PROJECT_NAME_MIN_LENGTH = 1;
export const PROJECT_NAME_MAX_LENGTH = 100;
export const PROJECT_DESCRIPTION_MAX_LENGTH = 2000;

export const PROJECTS_QUERY_KEY = "projects" as const;
export const CREATE_PROJECT_MUTATION_KEY = "createProject" as const;

/**
 * 403の画面表示メッセージ。
 * docs/detailed_design/api/projects/01_get_projects.md §エラー（403 USER_INACTIVE）
 * docs/detailed_design/api/projects/02_post_projects.md §エラー（403 USER_INACTIVE / CSRF_INVALID）
 */
export const FORBIDDEN_STATUS = 403;
export const USER_INACTIVE_CODE = "USER_INACTIVE" as const;
export const CSRF_INVALID_CODE = "CSRF_INVALID" as const;

export const FORBIDDEN_MESSAGES: Record<string, string> = {
	[USER_INACTIVE_CODE]: "アカウントが無効化されています。管理者にお問い合わせください",
	[CSRF_INVALID_CODE]: "セッションの検証に失敗しました。再度ログインしてからお試しください",
};
export const FORBIDDEN_FALLBACK_MESSAGE = "この操作を行う権限がありません";
