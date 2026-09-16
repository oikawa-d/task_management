export interface ProfileFormValues {
	last_name: string | null;
	first_name: string | null;
	last_name_kana: string | null;
	first_name_kana: string | null;
	birth_date: string | null;
}

export interface UserProfile extends ProfileFormValues {
	id: string;
	username: string;
	email: string;
	profile_completed: boolean;
	role: "member" | "admin";
	has_password: boolean;
	oauth_providers: string[];
}

export type ProfilePatchInput = Partial<{
	last_name: string;
	first_name: string;
	last_name_kana: string;
	first_name_kana: string;
	birth_date: string;
}>;

export interface PasswordChangeInput {
	current_password?: string;
	new_password: string;
	password_confirm: string;
}

export interface ApiFieldError {
	field: string;
	message: string;
}
