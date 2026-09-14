import { createContext, useContext, useState, type PropsWithChildren, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

import styles from "./SettingsPage.module.css";
import { FontSizeSelector } from "../components/FontSizeSelector";
import { LoginHistoryTable } from "../components/LoginHistoryTable";

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
