// Buttons (design-system.md, Components): secondary by default, primary at most once per
// view, ghost, danger (outlined, filled on hover), and the icon button, which always has a
// tooltip and an accessible name.

import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode, Ref } from "react";

import { cx } from "./cx";
import { Tip } from "./Tip";

type Tone = "secondary" | "primary" | "ghost" | "danger";
const SHAPE = "inline-flex h-ctl touch:h-ctl-touch items-center justify-center gap-2 rounded-m border px-3 " +
  "text-base font-medium whitespace-nowrap no-underline transition-colors " +
  "off:border-line off:bg-surface-2 off:text-ink-3";
const TONES: Record<Tone, string> = {
  secondary: "border-line-strong bg-surface-1 text-ink-1 hover:border-ink-1 hover:bg-surface-2 on:border-ink-1 on:bg-surface-3 open:border-ink-1 open:bg-surface-3",
  primary: "border-accent bg-accent font-semibold text-accent-ink hover:border-accent-hover hover:bg-accent-hover",
  ghost: "border-transparent bg-transparent text-ink-1 hover:bg-surface-3",
  danger: "border-danger bg-surface-1 text-danger hover:bg-danger hover:text-on-danger",
};

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { tone?: Tone; ref?: Ref<HTMLButtonElement> };
export function Button({ tone = "secondary", className, type = "button", ...rest }: ButtonProps) {
  return <button type={type} className={cx(SHAPE, TONES[tone], className)} {...rest} />;
}

type LinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & { tone?: Tone };
export function LinkButton({ tone = "secondary", className, ...rest }: LinkProps) {
  return <a className={cx(SHAPE, TONES[tone], className)} {...rest} />;
}

const ICON_SHAPE = "inline-grid flex-none place-items-center rounded-m border border-line-strong bg-surface-1 " +
  "p-0 text-ink-1 transition-colors hover:border-ink-1 hover:bg-surface-3 open:border-ink-1 open:bg-surface-3 " +
  "on:border-ink-1 on:bg-surface-3 off:border-line off:bg-surface-2 off:text-ink-3 touch:size-ctl-touch";

type IconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> & {
  label: string;       // the accessible name
  tip?: ReactNode;     // the tooltip when it should say more than the name
  small?: boolean;     // 28px, for rows
  ref?: Ref<HTMLButtonElement>;
};
export function IconButton({ label, tip, small, className, type = "button", ...rest }: IconButtonProps) {
  return (
    <Tip text={tip ?? label}>
      <button type={type} aria-label={label}
        className={cx(ICON_SHAPE, small ? "size-ctl-s" : "size-ctl-icon", className)} {...rest} />
    </Tip>
  );
}
