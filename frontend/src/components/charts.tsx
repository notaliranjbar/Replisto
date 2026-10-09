import { useEffect, useRef, useState, type ReactNode } from "react";
import { TrendingDown, TrendingUp } from "lucide-react";
import { cx } from "./ui";

// Small single-series charts for the insights page. One hue (the brand blue), thin marks,
// hairline grid, a hover tooltip on every chart, and a screen-reader table for each.

export type Point = { label: string; value: number; title?: string };

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth);
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** A clean maximum for the axis: 1, 2, 2.5 or 5 times a power of ten. */
function niceMax(value: number): number {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  for (const step of [1, 2, 2.5, 5, 10]) {
    if (value <= step * power) return step * power;
  }
  return 10 * power;
}

function SrTable({ points, caption, format }: { points: Point[]; caption: string; format: (v: number) => string }) {
  return (
    <table className="sr-only">
      <caption>{caption}</caption>
      <tbody>
        {points.map((p) => (
          <tr key={p.label}>
            <th scope="row">{p.title ?? p.label}</th>
            <td>{format(p.value)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Tooltip({ x, width, children }: { x: number; width: number; children: ReactNode }) {
  // keep the tooltip inside the chart
  const left = Math.min(Math.max(x, 64), Math.max(width - 64, 64));
  return (
    <div
      className="pointer-events-none absolute top-0 z-10 -translate-x-1/2 rounded-md border border-slate-200 bg-surface px-2.5 py-1.5 text-xs whitespace-nowrap shadow-lift"
      style={{ left }}
    >
      {children}
    </div>
  );
}

const PAD = { top: 12, right: 8, bottom: 22, left: 40 };

/** A line with a soft area under it, for a value over days. */
export function AreaChart({
  points,
  height = 190,
  caption,
  format,
}: {
  points: Point[];
  height?: number;
  caption: string;
  format: (v: number) => string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const max = niceMax(Math.max(...points.map((p) => p.value), 0));
  const innerW = Math.max(width - PAD.left - PAD.right, 1);
  const innerH = height - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (points.length > 1 ? (i / (points.length - 1)) * innerW : innerW / 2);
  const y = (v: number) => PAD.top + innerH - (v / max) * innerH;
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.value)}`).join(" ");
  const area = points.length ? `${line} L${x(points.length - 1)},${y(0)} L${x(0)},${y(0)} Z` : "";
  const ticks = [0, max / 2, max];
  const labelAt = new Set([0, Math.floor((points.length - 1) / 2), points.length - 1]);

  const onMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const rel = event.clientX - rect.left - PAD.left;
    const i = Math.round((rel / innerW) * (points.length - 1));
    setHover(Math.min(Math.max(i, 0), points.length - 1));
  };

  return (
    <div ref={ref} className="relative" dir="ltr">
      {width > 0 && points.length > 0 && (
        <svg width={width} height={height} role="img" aria-label={caption} onPointerMove={onMove} onPointerLeave={() => setHover(null)} className="touch-pan-y">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--color-line)" strokeWidth={1} />
              <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="num fill-slate-400 text-[11px]">
                {format(t)}
              </text>
            </g>
          ))}
          <path d={area} fill="var(--color-brand-500)" fillOpacity={0.1} />
          <path d={line} fill="none" stroke="var(--color-brand-500)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {points.map((p, i) =>
            labelAt.has(i) ? (
              <text key={p.label} x={x(i)} y={height - 6} textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"} className="fill-slate-400 text-[11px]">
                {p.label}
              </text>
            ) : null,
          )}
          {hover !== null && (
            <g>
              <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={y(0)} stroke="var(--color-slate-300)" strokeWidth={1} />
              <circle cx={x(hover)} cy={y(points[hover].value)} r={4.5} fill="var(--color-brand-500)" stroke="var(--color-surface)" strokeWidth={2} />
            </g>
          )}
        </svg>
      )}
      {hover !== null && (
        <Tooltip x={x(hover)} width={width}>
          <span className="text-slate-500">{points[hover].title ?? points[hover].label}</span>{" "}
          <span className="num font-semibold text-ink-950">{format(points[hover].value)}</span>
        </Tooltip>
      )}
      <SrTable points={points} caption={caption} format={format} />
    </div>
  );
}

/** Columns from one baseline; `strong` marks the columns the text talks about. */
export function ColumnChart({
  points,
  height = 150,
  caption,
  format,
  strong,
  every = 1,
}: {
  points: Point[];
  height?: number;
  caption: string;
  format: (v: number) => string;
  strong?: Set<number>;
  /** show every n-th x label */
  every?: number;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const max = niceMax(Math.max(...points.map((p) => p.value), 0));
  const innerW = Math.max(width - PAD.left - PAD.right, 1);
  const innerH = height - PAD.top - PAD.bottom;
  const band = innerW / Math.max(points.length, 1);
  const barW = Math.min(24, Math.max(band - 2, 2));
  const y = (v: number) => PAD.top + innerH - (v / max) * innerH;
  const cx0 = (i: number) => PAD.left + band * i + band / 2;
  const ticks = [0, max / 2, max];

  return (
    <div ref={ref} className="relative" dir="ltr">
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={caption} onPointerLeave={() => setHover(null)}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--color-line)" strokeWidth={1} />
              <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="num fill-slate-400 text-[11px]">
                {format(t)}
              </text>
            </g>
          ))}
          {points.map((p, i) => {
            const top = y(p.value);
            const h = Math.max(y(0) - top, p.value > 0 ? 2 : 0);
            const r = Math.min(4, h, barW / 2);
            const left = cx0(i) - barW / 2;
            const muted = strong && !strong.has(i);
            // rounded data end, square at the baseline
            const d = `M${left},${y(0)} V${y(0) - h + r} Q${left},${y(0) - h} ${left + r},${y(0) - h} H${left + barW - r} Q${left + barW},${y(0) - h} ${left + barW},${y(0) - h + r} V${y(0)} Z`;
            return (
              <g key={p.label} onPointerEnter={() => setHover(i)}>
                {/* a hit target wider and taller than the column */}
                <rect x={PAD.left + band * i} y={PAD.top} width={band} height={innerH} fill="transparent" />
                <path d={d} fill={muted ? "var(--color-brand-200)" : "var(--color-brand-500)"} opacity={hover === null || hover === i ? 1 : 0.6} />
                {i % every === 0 && (
                  <text x={cx0(i)} y={height - 6} textAnchor="middle" className="fill-slate-400 text-[11px]">
                    {p.label}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      )}
      {hover !== null && (
        <Tooltip x={cx0(hover)} width={width}>
          <span className="text-slate-500">{points[hover].title ?? points[hover].label}</span>{" "}
          <span className="num font-semibold text-ink-950">{format(points[hover].value)}</span>
        </Tooltip>
      )}
      <SrTable points={points} caption={caption} format={format} />
    </div>
  );
}

/** Horizontal bars with the value at the tip (formats, hashtags). */
export function BarList({ rows, format }: { rows: { label: ReactNode; value: number; hint?: string; key: string }[]; format: (v: number) => string }) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <ul className="space-y-3">
      {rows.map((row) => (
        <li key={row.key} title={row.hint}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
            <span className="min-w-0 truncate text-ink-900">{row.label}</span>
            <span className="num shrink-0 text-slate-500">{format(row.value)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-fill">
            <div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.max((row.value / max) * 100, 2)}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** "+12.5%" against the period before; green when the change is good. */
export function Delta({ value, label }: { value: number | null | undefined; label?: string }) {
  if (value === null || value === undefined) return null;
  const up = value >= 0;
  const Icon = up ? TrendingUp : TrendingDown;
  return (
    <span className={cx("inline-flex items-center gap-1 text-xs font-medium", up ? "text-emerald-700" : "text-red-700")} title={label}>
      <Icon className="size-3.5" aria-hidden />
      <span className="num" dir="ltr">
        {up ? "+" : ""}
        {value.toFixed(1)}%
      </span>
    </span>
  );
}
