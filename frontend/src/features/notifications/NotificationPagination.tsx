export interface NotificationPaginationProps {
	page: number;
	totalPages: number;
	onPageChange: (page: number) => void;
}

/** 通知パネルのページネーション。2ページ以上のときのみ描画する（呼び出し側で制御） */
export function NotificationPagination({ page, totalPages, onPageChange }: NotificationPaginationProps) {
	const pages = Array.from({ length: totalPages }, (_, index) => index + 1);

	return (
		<nav aria-label="通知ページ">
			<button type="button" onClick={() => onPageChange(page - 1)} disabled={page <= 1}>
				前へ
			</button>
			{pages.map((pageNumber) => (
				<button
					key={pageNumber}
					type="button"
					aria-current={pageNumber === page ? "page" : undefined}
					onClick={() => onPageChange(pageNumber)}
				>
					{pageNumber}
				</button>
			))}
			<button
				type="button"
				onClick={() => onPageChange(page + 1)}
				disabled={page >= totalPages}
			>
				次へ
			</button>
		</nav>
	);
}
