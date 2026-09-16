import { getAuthValidationConfig } from "../config/validationConfig";
import { countCharacterTypes } from "../validation";
import styles from "./PasswordStrengthMeter.module.css";

const STRENGTH_LABELS = ["未入力", "弱い", "やや弱い", "普通", "強い"] as const;

export interface PasswordStrengthMeterProps {
	password: string;
}

/** design doc: docs/detailed_design/screen/02_register.md §9.1 calcPasswordStrength */
export function calcPasswordStrength(password: string): 0 | 1 | 2 | 3 | 4 {
	if (password.length === 0) {
		return 0;
	}
	const { passwordMinLength } = getAuthValidationConfig();
	const typeCount = countCharacterTypes(password);
	if (password.length < passwordMinLength) {
		return 1;
	}
	if (typeCount <= 1) {
		return 1;
	}
	if (typeCount === 2) {
		return 2;
	}
	if (typeCount === 3) {
		return 3;
	}
	return 4;
}


export function PasswordStrengthMeter({ password }: PasswordStrengthMeterProps) {
	const strength = calcPasswordStrength(password);
	return (
		<div className={styles.meter} aria-live="polite">
			<div className={styles.bar}>
				<div className={styles.fill} data-strength={strength} style={{ width: `${strength * 25}%` }} />
			</div>
			<span className={styles.label}>{STRENGTH_LABELS[strength]}</span>
		</div>
	);
}
