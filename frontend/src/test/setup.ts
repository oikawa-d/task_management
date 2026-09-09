const nativeRequest = globalThis.Request;

if (nativeRequest) {
	class CompatibleRequest extends nativeRequest {
		constructor(input: RequestInfo | URL, init?: RequestInit) {
			super(input, init?.signal ? { ...init, signal: undefined } : init);
		}
	}

	globalThis.Request = CompatibleRequest;
}
