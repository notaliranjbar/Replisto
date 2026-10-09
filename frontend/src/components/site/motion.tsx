import { useEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from "react";
import { cx } from "../ui";

// One IntersectionObserver for the whole page instead of one per element.
const callbacks = new WeakMap<Element, () => void>();
let shared: IntersectionObserver | null = null;

function observe(el: Element, onEnter: () => void): () => void {
  if (typeof IntersectionObserver === "undefined") {
    onEnter();
    return () => {};
  }
  shared ??= new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        callbacks.get(entry.target)?.();
        callbacks.delete(entry.target);
        shared?.unobserve(entry.target);
      }
    },
    { rootMargin: "0px 0px -8% 0px" },
  );
  callbacks.set(el, onEnter);
  shared.observe(el);
  return () => {
    callbacks.delete(el);
    shared?.unobserve(el);
  };
}

/** True once the element has scrolled into view (never goes back to false). */
function useInView(ref: RefObject<Element | null>): boolean {
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || inView) return;
    return observe(el, () => setInView(true));
  }, [ref, inView]);
  return inView;
}

export function useReducedMotion(): boolean {
  const query = "(prefers-reduced-motion: reduce)";
  const [reduced, setReduced] = useState(() => typeof matchMedia !== "undefined" && matchMedia(query).matches);
  useEffect(() => {
    const mq = matchMedia(query);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

/** Fades and lifts its content in the first time it enters the viewport. */
export function Reveal({ children, className, delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref);
  return (
    <div ref={ref} className={cx("reveal", inView && "is-in", className)} style={{ "--reveal-delay": `${delay}ms` } as CSSProperties}>
      {children}
    </div>
  );
}
