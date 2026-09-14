import { QueryClient } from "@tanstack/react-query";

/** アプリ全体で共有するサーバー状態のキャッシュ。 */
export const queryClient = new QueryClient();
