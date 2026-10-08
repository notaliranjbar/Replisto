import { useI18n } from "../i18n";
import { cx } from "./ui";

/** The Replisto mark: a reply arrow in a speech bubble, on a teal tile (vector, sharp at any size). */
export function LogoMark({ px = 36, className, alt = "" }: { px?: number; className?: string; alt?: string }) {
  return (
    <img
      src="/brand/replisto-mark.svg"
      width={px}
      height={px}
      alt={alt}
      decoding="async"
      className={cx("aspect-square shrink-0 rounded-[24%]", className)}
      style={{ width: px, height: px }}
    />
  );
}

/** Mark + name. `tone` is the surface it sits on. */
export function Logo({ tone = "light", className, markClassName }: { tone?: "light" | "dark"; className?: string; markClassName?: string }) {
  const { t } = useI18n();
  return (
    <span className={cx("inline-flex items-center gap-2.5", className)}>
      <LogoMark className={markClassName} />
      <span className={cx("text-xl font-black", tone === "dark" ? "text-white" : "text-ink-900")}>{t.appName}</span>
    </span>
  );
}
