import { transferableAbortController } from "node:util";

const nodeAbortController = transferableAbortController();

globalThis.AbortController = nodeAbortController.constructor as typeof AbortController;
globalThis.AbortSignal = nodeAbortController.signal.constructor as typeof AbortSignal;

const nativeRequest = globalThis.Request;

if (nativeRequest) {
	class CompatibleRequest extends nativeRequest {
		constructor(input: RequestInfo | URL, init?: RequestInit) {
			super(input, init?.signal ? { ...init, signal: undefined } : init);
		}
	}

	globalThis.Request = CompatibleRequest;
}
