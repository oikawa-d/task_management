import { createContext, useContext, useEffect, useState, type PropsWithChildren, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { useAuthStore } from "../../../auth/authStore";
import { clearUserSessionState } from "../../../auth/sessionCleanup";
import { ApiError } from "../../../api/errors";
import { ROUTES } from "../../../routes";
import styles from "./SettingsPage.module.css";
import { FontSizeSelector } from "../components/FontSizeSelector";
import { LoginHistoryTable } from "../components/LoginHistoryTable";
import { PasswordChangeForm } from "../PasswordChangeForm";
import { ProfileForm } from "../ProfileForm";
import { useChangePassword } from "../hooks/useChangePassword";
import { useUpdateProfile } from "../hooks/useUpdateProfile";
import { useUserProfile } from "../hooks/useUserProfile";

type SettingsTab = "profile" | "password" | "display" | "history";

const SETTINGS_TABS: ReadonlyArray<{ id: SettingsTab; label: string }> = [
	{ id: "profile", label: "プロフィール" },
	{ id: "password", label: "パスワード" },
	{ id: "display", label: "表示設定" },
	{ id: "history", label: "ログイン履歴" },
];

export interface SettingsPageProps {
	profileCompleted?: boolean;
	profileForm?: ReactNode;
	passwordChangeForm?: ReactNode;
}

export type SettingsFormSlotProps = {
	onSuccess: (message: string) => void;
};

export type SettingsFormSlot = (props: SettingsFormSlotProps) => ReactNode;

export type SettingsFormSlots = {
	profile?: SettingsFormSlot;
	password?: SettingsFormSlot;
};

const SettingsFormsContext = createContext<SettingsFormSlots>({});

export function SettingsFormsProvider({
	slots,
	children,
}: PropsWithChildren<{ slots?: SettingsFormSlots }>) {
	return <SettingsFormsContext.Provider value={slots ?? {}}>{children}</SettingsFormsContext.Provider>;
}

export function ConnectedSettingsPage() {
	const profileQuery = useUserProfile();
	const updateProfile = useUpdateProfile();
	const changePassword = useChangePassword();
	const queryClient = useQueryClient();
	const navigate = useNavigate();
	const customSlots = useContext(SettingsFormsContext);
	const adapter = useAuthStore((state) => state.authAdapter);

	useEffect(() => {
		if (profileQuery.error instanceof ApiError && profileQuery.error.status === 401) {
			useAuthStore.getState().setUnauthenticated();
		}
	}, [profileQuery.error]);

	if (profileQuery.isLoading) return <p role="status">設定情報を読み込み中...</p>;
	if (profileQuery.isError || !profileQuery.data) {
		return <div role="alert">設定情報を読み込めませんでした。<button type="button" onClick={() => void profileQuery.refetch()}>再試行</button></div>;
	}

	const logoutAfterPasswordChange = async () => {
		try {
			await adapter?.logout();
		} catch {
			// 設計書どおりlogout失敗時もクライアントは未認証状態へ遷移する
		} finally {
			useAuthStore.getState().clear();
			clearUserSessionState(queryClient);
			navigate(ROUTES.LOGIN, { replace: true });
		}
	};
	const defaultSlots: SettingsFormSlots = {
		profile: ({ onSuccess }) => (
			<ProfileForm
				initialValues={profileQuery.data!}
				onSubmit={(values) => updateProfile.mutateAsync(values).then(() => undefined)}
				onSaved={() => onSuccess("プロフィールを更新しました")}
			/>
		),
		password: ({ onSuccess }) => (
			<PasswordChangeForm
				hasPassword={profileQuery.data!.has_password}
				onSubmit={(values) => changePassword.mutateAsync(values)}
				onSuccess={async () => {
					onSuccess("パスワードを変更しました");
					await logoutAfterPasswordChange();
				}}
			/>
		),
	};

	return (
		<SettingsFormsProvider slots={{ ...defaultSlots, ...customSlots }}>
			<SettingsPage profileCompleted={profileQuery.data.profile_completed} />
		</SettingsFormsProvider>
	);
}

function FormPlaceholder({ label }: { label: string }) {
	return (
		<form aria-label={`${label}フォーム`} className={styles.placeholder}>
			<p>{label}フォームを表示します。</p>
		</form>
	);
}

export function SettingsPage({
	profileCompleted = false,
	profileForm = <FormPlaceholder label="プロフィール編集" />,
	passwordChangeForm = <FormPlaceholder label="パスワード変更" />,
}: SettingsPageProps) {
	const { search } = useLocation();
	const formSlots = useContext(SettingsFormsContext);
	const [activeTab, setActiveTab] = useState<SettingsTab>("profile");
	const [successMessage, setSuccessMessage] = useState<string | null>(null);
	const isCompletionRequested = new URLSearchParams(search).get("complete_profile") === "1";
	const showCompletionBanner = !profileCompleted && isCompletionRequested;
	const handleFormSuccess = (message: string) => setSuccessMessage(message);
	const renderedProfileForm = formSlots.profile
		? formSlots.profile({ onSuccess: handleFormSuccess })
		: profileForm;
	const renderedPasswordChangeForm = formSlots.password
		? formSlots.password({ onSuccess: handleFormSuccess })
		: passwordChangeForm;
	const activeLabel = SETTINGS_TABS.find((tab) => tab.id === activeTab)?.label ?? "プロフィール";
	const changeTabByKeyboard = (currentTab: SettingsTab, key: string) => {
		const currentIndex = SETTINGS_TABS.findIndex((tab) => tab.id === currentTab);
		const nextIndex = key === "ArrowRight" || key === "ArrowDown"
			? (currentIndex + 1) % SETTINGS_TABS.length
			: (currentIndex - 1 + SETTINGS_TABS.length) % SETTINGS_TABS.length;
		const nextTab = SETTINGS_TABS[nextIndex].id;
		setActiveTab(nextTab);
		document.getElementById(`${nextTab}-tab`)?.focus();
	};

	return (
		<section className={styles.page} aria-labelledby="settings-heading">
			<h1 id="settings-heading">アカウント設定</h1>
			{showCompletionBanner ? (
				<p className={styles.banner} role="status">
					プロフィールを入力してください
				</p>
			) : null}
			{successMessage ? <p role="status">{successMessage}</p> : null}
			<div className={styles.tabs} role="tablist" aria-label="アカウント設定の項目">
				{SETTINGS_TABS.map((tab) => (
					<button
						aria-controls={`${tab.id}-panel`}
						aria-selected={activeTab === tab.id}
						className={styles.tab}
						id={`${tab.id}-tab`}
						key={tab.id}
						onClick={(event) => {
							setActiveTab(tab.id);
							event.currentTarget.focus();
						}}
						onKeyDown={(event) => {
							if (["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) {
								event.preventDefault();
								changeTabByKeyboard(tab.id, event.key);
							}
						}}
						role="tab"
						tabIndex={activeTab === tab.id ? 0 : -1}
						type="button"
					>
						{tab.label}
					</button>
				))}
			</div>
			<div
				aria-labelledby={`${activeTab}-tab`}
				className={styles.panel}
				id={`${activeTab}-panel`}
				role="tabpanel"
				tabIndex={-1}
			>
				<h2 id={`${activeTab}-heading`}>{activeLabel}</h2>
				{activeTab === "profile" ? renderedProfileForm : null}
				{activeTab === "password" ? renderedPasswordChangeForm : null}
				{activeTab === "display" ? <FontSizeSelector /> : null}
				{activeTab === "history" ? <LoginHistoryTable /> : null}
			</div>
		</section>
	);
}
