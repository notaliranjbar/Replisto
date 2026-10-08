import {
  useEffect,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type TextareaHTMLAttributes,
} from "react";
import { Link } from "react-router";
import { AlertTriangle, CheckCircle2, Info, Loader2, X, XCircle } from "lucide-react";
import { useI18n } from "../i18n";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "danger" | "ghost" | "soft" | "ink" | "inverse" | "outlineInverse" | "ghostInverse";
type Size = "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  primary: "bg-brand-600 text-white hover:bg-brand-deep shadow-sm hover:shadow-md hover:shadow-brand-600/25",
  secondary: "bg-surface text-ink-900 border border-slate-200 hover:border-brand-300 hover:text-brand-700 shadow-sm",
  danger: "bg-red-600 text-white hover:bg-red-500 shadow-sm",
  ghost: "text-slate-600 hover:bg-fill hover:text-ink-950",
  soft: "bg-brand-50 text-brand-700 hover:bg-brand-100",
  ink: "bg-night-900 text-white hover:bg-night-800 shadow-sm",
  // for violet and ink surfaces
  inverse: "bg-surface text-ink-900 hover:bg-brand-50 shadow-[0_1px_0_rgb(14_10_25/0.25),0_8px_24px_-8px_rgb(14_10_25/0.45)]",
  outlineInverse: "text-white border border-white/35 hover:bg-white/10 hover:border-white/60",
  ghostInverse: "text-white/90 hover:bg-white/10 hover:text-white",
};
const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-sm gap-1.5 rounded-lg font-medium",
  md: "h-10 px-4 text-sm gap-2 rounded-lg font-medium",
  lg: "h-12 px-6 text-[15px] gap-2 rounded-xl font-semibold",
};

/**
 * `extra` must not repeat a property the variant or size sets (Tailwind orders utilities by
 * property, not by class order). To hide a button responsively use `max-sm:hidden` etc.
 */
export function buttonClass(variant: Variant = "primary", size: Size = "md", extra?: string) {
  return cx(
    "group/btn inline-flex items-center justify-center whitespace-nowrap select-none",
    "transition-[background-color,border-color,color,box-shadow,transform] duration-200 ease-out active:scale-[0.97]",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500",
    "disabled:opacity-50 disabled:pointer-events-none",
    variants[variant],
    sizes[size],
    extra,
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
};

export function Button({ variant, size, loading, icon, className, children, disabled, type = "button", ...rest }: ButtonProps) {
  return (
    <button type={type} className={buttonClass(variant, size, className)} disabled={disabled || loading} {...rest}>
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

type LinkButtonProps = { to: string; variant?: Variant; size?: Size; icon?: ReactNode; children: ReactNode; className?: string };

export function LinkButton({ to, variant, size, icon, children, className }: LinkButtonProps) {
  return (
    <Link to={to} className={buttonClass(variant, size, className)}>
      {icon}
      {children}
    </Link>
  );
}

/** External link styled as a button; opens in a new tab. */
export function ExternalButton({ href, variant, size, icon, children, className }: Omit<LinkButtonProps, "to"> & { href: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={buttonClass(variant, size, className)}>
      {icon}
      {children}
    </a>
  );
}

/**
 * Panel surfaces share the public site's card language: 2xl radius, a hairline ring instead
 * of a grey border, and a soft violet-tinted shadow.
 */
export function Card({ className, children, danger }: { className?: string; children: ReactNode; danger?: boolean }) {
  return <div className={cx("rounded-2xl bg-surface shadow-soft ring-1", danger ? "ring-red-200" : "ring-line", className)}>{children}</div>;
}

/** Violet-tinted square holding a section icon (same as the site's demo cards). */
export function IconChip({ children, tone = "brand", className }: { children: ReactNode; tone?: "brand" | "solid" | "red" | "amber" | "green" | "ink"; className?: string }) {
  const tones = {
    brand: "bg-brand-50 text-brand-700",
    solid: "bg-brand-600 text-white shadow-md shadow-brand-600/25",
    red: "bg-red-50 text-red-700",
    amber: "bg-amber-50 text-amber-600",
    green: "bg-emerald-50 text-emerald-600",
    ink: "bg-white/10 text-accent-300",
  };
  return (
    <span aria-hidden className={cx("flex size-9 shrink-0 items-center justify-center rounded-xl [&>svg]:size-[18px]", tones[tone], className)}>
      {children}
    </span>
  );
}

export function CardHeader({ title, action, subtitle, icon }: { title: ReactNode; action?: ReactNode; subtitle?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4 sm:px-6">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        {icon && <IconChip>{icon}</IconChip>}
        <div className="min-w-0">
          <h2 className="font-bold text-ink-950">{title}</h2>
          {subtitle && <p className="mt-0.5 text-sm leading-6 text-slate-500">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  );
}

/** Page title in the site's heading style, with the page's icon on a solid violet chip. */
export function PageHeader({ title, subtitle, action, icon }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <header className="animate-pop-in mb-8 flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="flex min-w-0 items-start gap-4">
        {icon && (
          <IconChip tone="solid" className="mt-0.5 size-12 rounded-2xl max-sm:hidden [&>svg]:size-6">
            {icon}
          </IconChip>
        )}
        <div className="min-w-0">
          <h1 className="text-2xl font-extrabold text-ink-950 sm:text-[1.75rem] sm:leading-tight">{title}</h1>
          {subtitle && <p className="mt-1.5 max-w-2xl text-[15px] leading-7 text-slate-500">{subtitle}</p>}
        </div>
      </div>
      {action && <div className="flex flex-wrap items-center gap-2">{action}</div>}
    </header>
  );
}

type Tone = "neutral" | "brand" | "red" | "amber" | "green";
const badgeTones: Record<Tone, string> = {
  neutral: "bg-slate-100 text-slate-600",
  brand: "bg-brand-50 text-brand-700 ring-1 ring-brand-100",
  red: "bg-red-50 text-red-700 ring-1 ring-red-200",
  amber: "bg-amber-50 text-amber-800 ring-1 ring-amber-200",
  green: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap [&>svg]:size-3.5", badgeTones[tone], className)}>
      {children}
    </span>
  );
}

/** Small count bubble for the menu. */
export function CountBadge({ count, tone = "red" }: { count: string; tone?: "red" | "neutral" }) {
  return (
    <span
      className={cx(
        "num inline-flex min-w-5 items-center justify-center rounded-full px-1.5 text-xs font-bold leading-5",
        tone === "red" ? "bg-red-500 text-white" : "bg-slate-200 text-slate-700",
      )}
    >
      {count}
    </span>
  );
}

type AlertKind = "warning" | "error" | "info" | "success";
const alertStyles: Record<AlertKind, { box: string; icon: ReactNode }> = {
  warning: { box: "bg-amber-50 text-amber-900 ring-amber-200/80", icon: <AlertTriangle className="size-5 shrink-0 text-amber-500" /> },
  error: { box: "bg-red-50 text-red-800 ring-red-200/80", icon: <XCircle className="size-5 shrink-0 text-red-500" /> },
  info: { box: "bg-brand-50/70 text-ink-800 ring-brand-100", icon: <Info className="size-5 shrink-0 text-brand-500" /> },
  success: { box: "bg-emerald-50 text-emerald-900 ring-emerald-200/80", icon: <CheckCircle2 className="size-5 shrink-0 text-emerald-500" /> },
};

export function Alert({ kind = "info", children, action, className }: { kind?: AlertKind; children: ReactNode; action?: ReactNode; className?: string }) {
  const s = alertStyles[kind];
  return (
    <div role={kind === "error" ? "alert" : "status"} className={cx("flex flex-wrap items-start gap-3 rounded-xl px-4 py-3 text-sm leading-6 ring-1", s.box, className)}>
      {s.icon}
      <div className="min-w-0 flex-1 user-text">{children}</div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cx("size-5 animate-spin text-brand-400", className)} />;
}

export function PageLoading() {
  return (
    <div className="flex min-h-48 items-center justify-center" role="status">
      <Spinner className="size-7" />
    </div>
  );
}

/** Friendly "nothing here" block: icon in a soft violet circle, bold line, optional detail. */
export function EmptyState({ icon, title, children }: { icon?: ReactNode; title: ReactNode; children?: ReactNode }) {
  return (
    <div className="animate-pop-in flex flex-col items-center justify-center px-6 py-14 text-center">
      {icon && (
        <div aria-hidden className="mb-4 flex size-16 items-center justify-center rounded-full bg-brand-50 text-brand-500 ring-8 ring-brand-50/50 [&>svg]:size-7">
          {icon}
        </div>
      )}
      <p className="max-w-sm font-bold text-ink-900">{title}</p>
      {children && <div className="mt-1.5 max-w-sm text-sm leading-6 text-slate-500">{children}</div>}
    </div>
  );
}

type FieldProps = { label: ReactNode; hint?: ReactNode; error?: string; children: (id: string) => ReactNode; className?: string };

export function Field({ label, hint, error, children, className }: FieldProps) {
  const id = useId();
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-2 block text-sm font-semibold text-ink-900">
        {label}
      </label>
      {children(id)}
      {error ? (
        <p className="mt-1.5 text-xs font-medium text-red-700">{error}</p>
      ) : (
        hint && <p className="mt-1.5 text-xs leading-5 text-slate-500">{hint}</p>
      )}
    </div>
  );
}

const inputBase =
  "block w-full rounded-xl border bg-surface px-3.5 text-sm text-ink-950 placeholder:text-slate-400 transition-[border-color,box-shadow] duration-200 hover:border-slate-300 focus:outline-none focus:ring-4 focus:ring-brand-500/15 disabled:bg-slate-50";

export function Input({ invalid, className, ...rest }: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return (
    <input
      className={cx(inputBase, "h-11", invalid ? "border-red-400" : "border-slate-200 focus:border-brand-500", className)}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  );
}

export function Textarea({ invalid, className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }) {
  return (
    <textarea
      className={cx(inputBase, "py-2.5 leading-7", invalid ? "border-red-400" : "border-slate-200 focus:border-brand-500", className)}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  );
}

export function Select({ className, children, ...rest }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cx(inputBase, "h-11 border-slate-200 focus:border-brand-500", className)} {...rest}>
      {children}
    </select>
  );
}

export function Toggle({
  checked,
  onChange,
  disabled,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx(
        // a 44px-tall touch area around the 24px track
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full px-0.5 transition-colors duration-200 after:absolute after:-inset-x-1 after:-inset-y-2.5 after:content-['']",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 disabled:opacity-50",
        checked ? "bg-emerald-500" : "bg-slate-300 hover:bg-slate-400/80",
      )}
    >
      {/* knob slides from the start edge to the end edge (mirrored in RTL) */}
      <span
        className={cx(
          "inline-block size-5 rounded-full bg-white shadow transition-transform duration-200 ease-[var(--ease-out-soft)]",
          checked && "translate-x-5 rtl:-translate-x-5",
        )}
      />
    </button>
  );
}

export function Tabs<T extends string>({
  value,
  onChange,
  items,
  compact,
}: {
  value: T;
  onChange: (v: T) => void;
  items: { value: T; label: ReactNode; count?: string }[];
  /** compact: tighter tabs that share the full width (narrow columns like the inbox list) */
  compact?: boolean;
}) {
  return (
    <div
      role="tablist"
      className={cx(
        "max-w-full gap-1 overflow-x-auto rounded-xl bg-fill p-1 no-scrollbar",
        compact ? "flex w-full [&>button]:flex-1 [&>button]:justify-center [&>button]:px-2 [&>button]:text-[13px]" : "inline-flex",
      )}
    >
      {items.map((it) => {
        const on = value === it.value;
        return (
          <button
            key={it.value}
            role="tab"
            type="button"
            aria-selected={on}
            onClick={() => onChange(it.value)}
            className={cx(
              "flex min-h-9 items-center gap-1.5 whitespace-nowrap rounded-lg px-3.5 text-sm font-semibold transition-[color,background-color,box-shadow] duration-200",
              on ? "bg-surface text-ink-950 shadow-sm" : "text-slate-500 hover:text-ink-900",
            )}
          >
            {it.label}
            {it.count && (
              <span className={cx("num rounded-full px-1.5 text-xs leading-5", on ? "bg-brand-600 text-white" : "bg-slate-200/80 text-slate-600")}>{it.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "md" | "lg";
}) {
  const { t } = useI18n();
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      d.showModal();
      // React's autoFocus runs before showModal, which then moves focus; mark fields with data-autofocus instead
      d.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    }
    if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      className={cx(
        "m-auto w-[calc(100%-2rem)] rounded-2xl bg-surface p-0 text-ink-950 shadow-float backdrop:bg-night-950/45 backdrop:backdrop-blur-[2px]",
        size === "lg" ? "max-w-2xl" : "max-w-md",
      )}
    >
      {open && (
        <div className="flex max-h-[85vh] flex-col">
          <div className="flex items-center justify-between gap-3 px-6 pb-2 pt-5">
            <h2 className="text-lg font-extrabold text-ink-950">{title}</h2>
            <button
              type="button"
              onClick={onClose}
              aria-label={t.common.close}
              className="-me-2 inline-flex size-9 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-ink-900"
            >
              <X className="size-5" />
            </button>
          </div>
          <div className="overflow-y-auto px-6 py-3">{children}</div>
          {footer && <div className="flex flex-wrap justify-end gap-2 px-6 pb-5 pt-3">{footer}</div>}
        </div>
      )}
    </dialog>
  );
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  body,
  confirmLabel,
  cancelLabel,
  danger,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: ReactNode;
  body: ReactNode;
  confirmLabel: string;
  cancelLabel: string;
  danger?: boolean;
  loading?: boolean;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {cancelLabel}
          </Button>
          <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-sm leading-7 text-slate-600">{body}</div>
    </Modal>
  );
}

export function ProgressBar({ value, max, tone }: { value: number; max: number; tone?: "brand" | "amber" | "red" }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  const auto = pct >= 100 ? "red" : pct >= 85 ? "amber" : "brand";
  const color = { brand: "bg-brand-500", amber: "bg-amber-500", red: "bg-red-500" }[tone ?? auto];
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-fill" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={max}>
      <div className={cx("h-full rounded-full transition-[width] duration-700 ease-[var(--ease-out-soft)]", color)} style={{ width: `${pct}%` }} />
    </div>
  );
}
