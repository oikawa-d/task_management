const LOGIN_MESSAGE_KEY = "cerberus.login.message";

export function setLoginMessage(message: string): void {
	sessionStorage.setItem(LOGIN_MESSAGE_KEY, message);
}

export function consumeLoginMessage(): string | null {
	const message = sessionStorage.getItem(LOGIN_MESSAGE_KEY);
	sessionStorage.removeItem(LOGIN_MESSAGE_KEY);
	return message;
}
