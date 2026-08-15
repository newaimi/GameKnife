import { clampProgressValue } from "./feedback.js";

export function ProgressBar({ value, label, tone = "info" }: { value: number; label: string; tone?: "info" | "success" | "danger" }) {
  const progress = clampProgressValue(value);
  return (
    <div
      className={`gk-progress gk-progress--${tone}`}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={progress}
    >
      <span style={{ width: `${progress}%` }} />
    </div>
  );
}
