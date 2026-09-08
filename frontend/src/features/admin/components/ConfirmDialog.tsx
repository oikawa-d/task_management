interface ConfirmDialogProps {
	open: boolean;
	title: string;
	message: string;
	confirmLabel: string;
	cancelLabel: string;
	errorMessage?: string | null;
	isSubmitting?: boolean;
	onConfirm: () => void;
	onCancel: () => void;
}

function ConfirmDialog({
	open,
	title,
	message,
	confirmLabel,
	cancelLabel,
	errorMessage,
	isSubmitting = false,
	onConfirm,
	onCancel,
}: ConfirmDialogProps) {
	if (!open) {
		return null;
	}

	return (
		<div role="alertdialog" aria-modal="true" aria-label={title}>
			<h2>{title}</h2>
			<p>{message}</p>
			{errorMessage ? <p role="alert">{errorMessage}</p> : null}
			<button type="button" onClick={onCancel} disabled={isSubmitting}>
				{cancelLabel}
			</button>
			<button type="button" onClick={onConfirm} disabled={isSubmitting}>
				{confirmLabel}
			</button>
		</div>
	);
}

export default ConfirmDialog;
