import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "quiet" | "danger";
export type ButtonSize = "small" | "medium";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
};

/**
 * GameKnife 各工作流共用的按钮入口。变体只表达操作层级，具体业务是否可执行仍由调用方决定，
 * 这样 Community 与 Commercial 可以共享交互反馈，同时保留各自的权限校验和业务状态。
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
 * 只显示图标的按钮必须提供可访问名称。统一入口可以避免工具栏在视觉上足够紧凑时，
 * 键盘和读屏用户却无法判断按钮用途。
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
