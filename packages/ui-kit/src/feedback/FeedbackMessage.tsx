import type { HTMLAttributes, ReactNode } from "react";
import type { StatusTone } from "./StatusBadge";

export function FeedbackMessage({ tone = "info", title, className, children, ...props }: HTMLAttributes<HTMLDivElement> & { tone?: StatusTone; title?: string; children: ReactNode }) {
  const classes = ["gk-feedback-message", `gk-feedback-message--${tone}`, className].filter(Boolean).join(" ");
  return (
    <div className={classes} role={tone === "danger" ? "alert" : "status"} {...props}>
      {title ? <strong>{title}</strong> : null}
      <div>{children}</div>
    </div>
  );
}
