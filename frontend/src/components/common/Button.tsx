import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router";

import s from "./common.module.css";
import { Icon, type IconName } from "./Icon";

type Variant = "primary" | "secondary" | "quiet";

export function Button({
  variant = "secondary",
  icon,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; icon?: IconName; children: ReactNode }) {
  return (
    <button type="button" className={`${s.btn} ${s[variant]}`} {...rest}>
      {children}
      {icon && <Icon name={icon} size={16} />}
    </button>
  );
}

export function LinkButton({
  variant = "secondary",
  icon,
  children,
  ...rest
}: LinkProps & { variant?: Variant; icon?: IconName; children: ReactNode }) {
  return (
    <Link className={`${s.btn} ${s[variant]}`} {...rest}>
      {children}
      {icon && <Icon name={icon} size={16} />}
    </Link>
  );
}
