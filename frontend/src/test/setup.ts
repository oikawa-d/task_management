import { transferableAbortController } from "node:util";

const nodeAbortController = transferableAbortController();

globalThis.AbortController = nodeAbortController.constructor as typeof AbortController;
globalThis.AbortSignal = nodeAbortController.signal.constructor as typeof AbortSignal;
