import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "quiet" | "danger";
export type ButtonSize = "small" | "medium";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
};

/**
 * Shared button entry point for GameKnife workflows. Variants express only action hierarchy; callers pass
 * permission results and business state through native button properties while the component standardizes feedback.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "secondary", size = "medium", type = "button", ...props },
  ref,
) {
  const classes = ["gk-button", `gk-button--${variant}`, `gk-button--${size}`, className].filter(Boolean).join(" ");
  return <button ref={ref} className={classes} type={type} {...props} />;
});

export type IconButtonProps = Omit<ButtonProps, "aria-label" | "children"> & {
  label: string;
  children: ReactNode;
};

/**
 * Icon-only buttons must expose an accessible name. A shared entry point keeps compact toolbars understandable
 * to keyboard and screen-reader users.
 */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { className, label, variant = "quiet", size = "small", children, ...props },
  ref,
) {
  const classes = ["gk-icon-button", className].filter(Boolean).join(" ");
  return (
    <Button ref={ref} className={classes} variant={variant} size={size} aria-label={label} title={label} {...props}>
      {children}
    </Button>
  );
});
