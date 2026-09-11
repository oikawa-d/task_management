import { fetchWithAuth } from "../../../api/authAdapter/client";
import type { NotificationItemData } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

interface NotificationResponse {
	id: string;
	type: NotificationItemData["type"];
	title: string;
	body: string | null;
	task: { id: string; project_id: string | null; title: string } | null;
	due_at: string | null;
	read_at: string | null;
	created_at: string;
}

interface NotificationListResponse {
	items: NotificationResponse[];
	meta: { page: number; total_pages: number };
	unread_count: number;
}

function toItem(item: NotificationResponse): NotificationItemData {
	return {
		id: item.id,
		type: item.type,
		title: item.title,
		body: item.body,
		task: item.task ? { id: item.task.id, projectId: item.task.project_id, title: item.task.title } : null,
		dueAt: item.due_at,
		readAt: item.read_at,
		createdAt: item.created_at,
	};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
	const response = await fetchWithAuth(`${API_BASE_URL}${path}`, {
		...init,
		headers: { Accept: "application/json", ...init.headers },
	}, API_BASE_URL);
	if (!response.ok) throw new Error(`通知APIエラー: ${response.status}`);
	return (await response.json()) as T;
}

export async function getNotifications(page: number): Promise<{ items: NotificationItemData[]; totalPages: number }> {
	const response = await request<NotificationListResponse>(`/notifications?page=${page}&per_page=20`);
	return { items: response.items.map(toItem), totalPages: response.meta.total_pages };
}

export async function markNotificationRead(notificationId: string): Promise<{ unreadCount: number }> {
	const response = await request<{ unread_count: number }>(`/notifications/${notificationId}/read`, { method: "PATCH" });
	return { unreadCount: response.unread_count };
}

export async function markAllNotificationsRead(): Promise<{ unreadCount: number }> {
	const response = await request<{ unread_count: number }>("/notifications/read-all", { method: "POST" });
	return { unreadCount: response.unread_count };
}
