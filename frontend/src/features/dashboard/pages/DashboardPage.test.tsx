import "@testing-library/jest-dom/vitest";

import type { AxiosInstance } from "axios";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetApiClient } from "../../../api/client";
import { clearAuthAdapter, setAuthAdapterMode } from "../../../api/authAdapter/client";
import { useProjectStore } from "../../../stores/projectStore";
import { ApiError } from "../../../api/errors";
import type { ProjectSummary } from "../api/types";
import { DashboardPage } from "./DashboardPage";

function createMockClient(): AxiosInstance {
	return {
		get: vi.fn(),
		post: vi.fn(),
		interceptors: {
			request: { use: vi.fn() },
			response: { use: vi.fn() },
		},
	} as unknown as AxiosInstance;
}

function installFetchClient(client: AxiosInstance): void {
	setAuthAdapterMode("session");
	vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
		const requestUrl = new URL(String(input), "http://localhost");
		const path = requestUrl.pathname.replace(/^\/api/, "");
		const rawParams = Object.fromEntries(requestUrl.searchParams.entries());
		const params = path === "/projects"
			? { page: Number(rawParams.page), per_page: Number(rawParams.per_page), include_inactive: rawParams.include_inactive === "true" }
			: rawParams;
		try {
			const method = init?.method?.toUpperCase() ?? "GET";
			const result = method === "POST"
				? await client.post(path, JSON.parse(String(init?.body ?? "{}")))
				: path === "/tasks/calendar"
					? await client.get(path, { params })
					: await client.get(path, { params });
			return new Response(JSON.stringify(result?.data ?? []), { status: 200 });
		} catch (error) {
			if (!(error instanceof ApiError)) throw error;
			return new Response(JSON.stringify({ error: { code: error.code, message: error.message, details: error.details } }), { status: error.status ?? 500 });
		}
	}));
}

function buildProject(overrides: Partial<ProjectSummary> = {}): ProjectSummary {
	return {
		id: "project-1",
		name: "Cerberus開発",
		description: "学習用タスク管理システムの開発",
		owner: { id: "user-1", username: "taro", display_name: "山田 太郎" },
		member_count: 3,
		task_counts: { todo: 4, in_progress: 2, done: 7 },
		is_owner: true,
		is_active: true,
		start_at: null,
		end_at: null,
		created_at: "2026-09-01T00:00:00Z",
		...overrides,
	};
}

function renderDashboard() {
	const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
	function LocationDisplay() {
		const location = useLocation();
		return <output data-testid="location">{location.pathname}</output>;
	}
	render(
		<QueryClientProvider client={queryClient}>
			<MemoryRouter>
				<DashboardPage />
				<LocationDisplay />
			</MemoryRouter>
		</QueryClientProvider>,
	);
}

describe("DashboardPage", () => {
	beforeEach(() => {
		useProjectStore.getState().clearSelectedProject();
	});

	afterEach(() => {
		vi.restoreAllMocks();
		vi.unstubAllGlobals();
		clearAuthAdapter();
		resetApiClient();
	});

	it("読み込み中はステータス表示を出す", async () => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
		installFetchClient(client);

		renderDashboard();

		expect(screen.getByText("読み込み中です…")).toBeInTheDocument();
	});

	it("0件時は空状態メッセージと作成導線を表示する", async () => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
			data: { items: [], meta: { page: 1, per_page: 20, total: 0, total_pages: 0 } },
		});
		installFetchClient(client);

		renderDashboard();

		expect(await screen.findByText("まだプロジェクトがありません。")).toBeInTheDocument();
	});

	it("取得成功時はGET /api/projectsの実データをカードとして描画する", async () => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
			data: { items: [buildProject()], meta: { page: 1, per_page: 20, total: 1, total_pages: 1 } },
		});
		installFetchClient(client);

		renderDashboard();

		expect(await screen.findByRole("button", { name: "Cerberus開発" })).toBeInTheDocument();
		expect(screen.getByText("メンバー 3人")).toBeInTheDocument();
		expect(client.get).toHaveBeenCalledWith("/projects", { params: { page: 1, per_page: 20, include_inactive: false } });
	});

	it("プロジェクト選択時にboardへ遷移する", async () => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
			data: { items: [buildProject()], meta: { page: 1, per_page: 20, total: 1, total_pages: 1 } },
		});
		installFetchClient(client);

		renderDashboard();
		fireEvent.click(await screen.findByRole("button", { name: "Cerberus開発" }));

		expect(screen.getByTestId("location").textContent).toBe("/projects/project-1");
	});

	it("取得失敗時はエラー表示と再試行導線を表示し、再試行でrefetchする", async () => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>)
			.mockRejectedValueOnce(new ApiError({ code: "INTERNAL_ERROR", message: "サーバーエラー", status: 500 }))
			.mockResolvedValueOnce({ data: [] })
			.mockResolvedValueOnce({
				data: { items: [buildProject()], meta: { page: 1, per_page: 20, total: 1, total_pages: 1 } },
			});
		installFetchClient(client);

		renderDashboard();

		expect(await screen.findByText("プロジェクト一覧の取得に失敗しました。")).toBeInTheDocument();

		fireEvent.click(screen.getByRole("button", { name: "再試行" }));

		expect(await screen.findByRole("button", { name: "Cerberus開発" })).toBeInTheDocument();
		expect(client.get).toHaveBeenCalledTimes(3);
	});

	it("作成成功時はモーダルを閉じ、一覧を再取得する", async () => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>)
			.mockResolvedValueOnce({ data: { items: [], meta: { page: 1, per_page: 20, total: 0, total_pages: 0 } } })
			.mockResolvedValueOnce({ data: [] })
			.mockResolvedValueOnce({
				data: { items: [buildProject({ name: "新プロジェクト" })], meta: { page: 1, per_page: 20, total: 1, total_pages: 1 } },
			});
		(client.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: buildProject({ name: "新プロジェクト" }) });
		installFetchClient(client);

		renderDashboard();
		await screen.findByText("まだプロジェクトがありません。");

		fireEvent.click(screen.getByRole("button", { name: "プロジェクトを作成" }));
		fireEvent.change(screen.getByLabelText("プロジェクト名"), { target: { value: "新プロジェクト" } });
		fireEvent.click(screen.getByRole("button", { name: "作成" }));

		await waitFor(() => expect(client.post).toHaveBeenCalledWith("/projects", { name: "新プロジェクト", description: null }));
		await waitFor(() => expect(screen.queryByLabelText("プロジェクト名")).not.toBeInTheDocument());
		expect(await screen.findByRole("button", { name: "新プロジェクト" })).toBeInTheDocument();
		expect(client.get).toHaveBeenCalledTimes(3);
	});

	it("作成422時はフィールドエラーを表示し、モーダルは開いたままにする", async () => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
			data: { items: [], meta: { page: 1, per_page: 20, total: 0, total_pages: 0 } },
		});
		(client.post as ReturnType<typeof vi.fn>).mockRejectedValue(
			new ApiError({
				code: "VALIDATION_ERROR",
				message: "入力内容に誤りがあります",
				status: 422,
				details: [{ field: "name", message: "プロジェクト名を1〜100文字で入力してください" }],
			}),
		);
		installFetchClient(client);

		renderDashboard();
		await screen.findByText("まだプロジェクトがありません。");

		fireEvent.click(screen.getByRole("button", { name: "プロジェクトを作成" }));
		fireEvent.change(screen.getByLabelText("プロジェクト名"), { target: { value: "x" } });
		fireEvent.click(screen.getByRole("button", { name: "作成" }));

		expect(await screen.findByText("プロジェクト名を1〜100文字で入力してください")).toBeInTheDocument();
		expect(screen.getByLabelText("プロジェクト名")).toBeInTheDocument();
	});

	it("nameが101文字以上のときはクライアント側検証で送信を止める", async () => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
			data: { items: [], meta: { page: 1, per_page: 20, total: 0, total_pages: 0 } },
		});
		installFetchClient(client);

		renderDashboard();
		await screen.findByText("まだプロジェクトがありません。");

		fireEvent.click(screen.getByRole("button", { name: "プロジェクトを作成" }));
		fireEvent.change(screen.getByLabelText("プロジェクト名"), { target: { value: "a".repeat(101) } });
		fireEvent.click(screen.getByRole("button", { name: "作成" }));

		expect(await screen.findByText("プロジェクト名を1〜100文字で入力してください")).toBeInTheDocument();
		expect(client.post).not.toHaveBeenCalled();
	});
	it("プロジェクト選択時にprojectStoreへ選択を反映する", async () => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
			data: { items: [buildProject()], meta: { page: 1, per_page: 20, total: 1, total_pages: 1 } },
		});
		installFetchClient(client);

		renderDashboard();
		fireEvent.click(await screen.findByRole("button", { name: "Cerberus開発" }));

		expect(useProjectStore.getState().selectedProjectId).toBe("project-1");
	});

	it("作成成功時は作成したプロジェクトを選択stateへ反映する", async () => {
		const created = buildProject({ id: "project-9", name: "新プロジェクト" });
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>)
			.mockResolvedValueOnce({ data: { items: [], meta: { page: 1, per_page: 20, total: 0, total_pages: 0 } } })
			.mockResolvedValueOnce({ data: [] })
			.mockResolvedValueOnce({ data: { items: [created], meta: { page: 1, per_page: 20, total: 1, total_pages: 1 } } });
		(client.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: created });
		installFetchClient(client);

		renderDashboard();
		await screen.findByText("まだプロジェクトがありません。");

		fireEvent.click(screen.getByRole("button", { name: "プロジェクトを作成" }));
		fireEvent.change(screen.getByLabelText("プロジェクト名"), { target: { value: "新プロジェクト" } });
		fireEvent.click(screen.getByRole("button", { name: "作成" }));

		await waitFor(() => expect(useProjectStore.getState().selectedProjectId).toBe("project-9"));
		expect(await screen.findByRole("button", { name: "新プロジェクト" })).toHaveAttribute("aria-current", "true");
	});

	it("一覧取得403 USER_INACTIVEは個別メッセージを表示し、再試行導線を出さない", async () => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) =>
			url === "/projects"
				? Promise.reject(new ApiError({ code: "USER_INACTIVE", message: "アカウントが無効化されています", status: 403 }))
				: Promise.resolve({ data: [] }),
		);
		installFetchClient(client);

		renderDashboard();

		const listSection = within(screen.getByRole("region", { name: "プロジェクト一覧" }));
		expect(await listSection.findByText("アカウントが無効化されています。管理者にお問い合わせください")).toBeInTheDocument();
		expect(listSection.queryByRole("button", { name: "再試行" })).not.toBeInTheDocument();
	});

	it("作成403 CSRF_INVALIDはフォーム内へメッセージを表示し、フォームを開いたままにする", async () => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
			data: { items: [], meta: { page: 1, per_page: 20, total: 0, total_pages: 0 } },
		});
		(client.post as ReturnType<typeof vi.fn>).mockRejectedValue(
			new ApiError({ code: "CSRF_INVALID", message: "CSRFトークンが不正です", status: 403 }),
		);
		installFetchClient(client);

		renderDashboard();
		await screen.findByText("まだプロジェクトがありません。");

		fireEvent.click(screen.getByRole("button", { name: "プロジェクトを作成" }));
		fireEvent.change(screen.getByLabelText("プロジェクト名"), { target: { value: "新プロジェクト" } });
		fireEvent.click(screen.getByRole("button", { name: "作成" }));

		expect(await screen.findByText("セッションの検証に失敗しました。再度ログインしてからお試しください")).toBeInTheDocument();
		expect(screen.getByLabelText("プロジェクト名")).toBeInTheDocument();
		expect(useProjectStore.getState().selectedProjectId).toBeNull();
	});
});
