import type { TokenStore } from "../api/authAdapter";

let accessToken: string | null = null;

export const authTokenStore: TokenStore = {
	getAccessToken: () => accessToken,
	setAccessToken: (token) => {
		accessToken = token;
	},
};
