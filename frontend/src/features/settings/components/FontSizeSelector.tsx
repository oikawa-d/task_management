import { useEffect } from "react";

import { FONT_SCALE_OPTIONS } from "../config/displayConfig";
import { useUiStore } from "../../../stores/uiStore";

export function FontSizeSelector() {
	const fontScale = useUiStore((state) => state.fontScale);
	const setFontScale = useUiStore((state) => state.setFontScale);

	useEffect(() => {
		document.documentElement.style.setProperty("--font-scale", String(fontScale));
	}, [fontScale]);

	return (
		<fieldset>
			<legend>文字サイズ</legend>
			{FONT_SCALE_OPTIONS.map((option) => (
				<label key={option.value}>
					<input
						type="radio"
						name="font-scale"
						value={option.value}
						checked={fontScale === option.value}
						onChange={() => setFontScale(option.value)}
					/>
					{option.label}
				</label>
			))}
		</fieldset>
	);
}
