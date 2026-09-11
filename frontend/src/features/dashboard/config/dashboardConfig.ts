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
