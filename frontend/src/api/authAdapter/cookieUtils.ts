/** document.cookie から指定した名前のCookie値を読み取る。存在しない場合は null */
export function readCookie(name: string): string | null {
	if (typeof document === "undefined") {
		return null;
	}

	const escapedName = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
	const match = document.cookie.match(new RegExp(`(?:^|; )${escapedName}=([^;]*)`));

	return match ? decodeURIComponent(match[1]) : null;
}
