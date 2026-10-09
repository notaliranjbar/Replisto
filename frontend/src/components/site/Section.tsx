import type { ReactNode } from "react";
import { cx } from "../ui";
import { Reveal } from "./motion";

type Tone = "white" | "tint" | "ink";

const tones: Record<Tone, string> = {
  white: "bg-surface",
  tint: "bg-canvas border-y border-slate-200/70",
  ink: "bg-night-950 text-white",
};

export function Section({
  id,
  tone = "white",
  compact,
  className,
  children,
}: {
  id?: string;
  tone?: Tone;
  /** less vertical space, for supporting bands that shouldn't compete with the main sections */
  compact?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      aria-labelledby={id ? `${id}-title` : undefined}
      className={cx(compact ? "py-[clamp(3.5rem,7vw,5.5rem)]" : "py-[clamp(4.5rem,10vw,8rem)]", tones[tone], className)}
    >
      <div className="container-site">{children}</div>
    </section>
  );
}

export function SectionHeader({
  id,
  eyebrow,
  title,
  lead,
  align = "center",
  dark,
  className,
}: {
  id?: string;
  eyebrow?: string;
  title: ReactNode;
  lead?: ReactNode;
  align?: "center" | "start";
  dark?: boolean;
  className?: string;
}) {
  return (
    <Reveal className={cx("max-w-2xl", align === "center" && "mx-auto text-center", className)}>
      {eyebrow && <p className={cx("mb-3 text-[13px] font-semibold uppercase tracking-wider", dark ? "text-[#93b1fb]" : "text-brand-600")}>{eyebrow}</p>}
      <h2 id={id ? `${id}-title` : undefined} className={cx("t-h2 text-balance", dark ? "text-white" : "text-ink-950")}>
        {title}
      </h2>
      {lead && <p className={cx("t-lead mt-4 text-pretty", dark ? "text-white/70" : "text-slate-600")}>{lead}</p>}
    </Reveal>
  );
}

/** Small check-list used beside feature demos. */
export function Bullets({ items, className }: { items: readonly string[]; className?: string }) {
  return (
    <ul className={cx("space-y-3", className)}>
      {items.map((item) => (
        <li key={item} className="flex gap-3 text-[15px] leading-7 text-slate-700">
          <span aria-hidden className="mt-[0.65rem] size-1.5 shrink-0 rounded-[2px] bg-brand-600" />
          {item}
        </li>
      ))}
    </ul>
  );
}
