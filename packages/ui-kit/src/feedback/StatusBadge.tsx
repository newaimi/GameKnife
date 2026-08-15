import type { HTMLAttributes, ReactNode } from "react";

export type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";

export function StatusBadge({ tone = "neutral", busy = false, className, children, ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: StatusTone; busy?: boolean; children: ReactNode }) {
  const classes = ["gk-status-badge", `gk-status-badge--${tone}`, busy ? "gk-status-badge--busy" : "", className].filter(Boolean).join(" ");
  return (
    <span className={classes} {...props}>
      <i aria-hidden="true" />
      <span>{children}</span>
    </span>
  );
}
