import { useEffect, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, FileSpreadsheet, Info, Sheet, Upload } from "lucide-react";
import { api, apiUrl } from "../api/client";
import { keys } from "../api/queries";
import type { Preview, ProductField, Source } from "../api/types";
import { useI18n, type Lang } from "../i18n";
import { errorMessage } from "../lib/errors";
import { useToast } from "./toast";
import { Alert, Badge, Button, Card, Field, Input, PageLoading, Select, cx } from "./ui";

export type Kind = "google_sheet" | "upload";
type Mapping = Record<string, string>;
export type WizardStart = { kind?: Kind; url?: string; mapping?: Mapping };

// The panel uses its own field labels, translated.
const FIELD_LABELS: Record<Lang, Record<string, string>> = {
  en: {
    name: "Product name",
    sku: "Product code",
    category: "Category",
    color: "Color",
    size: "Size",
    price: "Price",
    stock: "Stock",
    description: "Description",
  },
  ar: {
    name: "اسم المنتج",
    sku: "رمز المنتج",
    category: "الفئة",
    color: "اللون",
    size: "المقاس",
    price: "السعر",
    stock: "المخزون",
    description: "الوصف",
  },
};

/** Connect products in three steps: pick a source, check the preview, map the columns. */
export default function ProductWizard({ start, onCancel, onDone }: { start: WizardStart; onCancel?: () => void; onDone: () => void }) {
  const { t, f } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [kind, setKind] = useState<Kind>(start.kind ?? "google_sheet");
  const [url, setUrl] = useState(start.url ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Mapping>({});
  const fileInput = useRef<HTMLInputElement>(null);

  const fields = useQuery({ queryKey: keys.fields, queryFn: () => api<ProductField[]>("/products/fields"), staleTime: Infinity });

  const runPreview = useMutation({
    mutationFn: () => {
      if (kind === "google_sheet") return api<Preview>("/products/sheet/preview", { method: "POST", json: { url: url.trim() } });
      const form = new FormData();
      form.append("file", file!);
      return api<Preview>("/products/file/preview", { method: "POST", form });
    },
    onSuccess: (p) => {
      setPreview(p);
      // keep the current mapping where those columns still exist, fill the rest from the suggestion
      const next: Mapping = Object.fromEntries(Object.entries(start.mapping ?? {}).filter(([, col]) => p.headers.includes(col)));
      for (const [field, col] of Object.entries(p.suggested_mapping)) {
        if (!next[field] && !Object.values(next).includes(col)) next[field] = col;
      }
      setMapping(next);
      setStep(2);
    },
  });

  // "Change columns" on a connected sheet jumps straight to the preview
  const autoRan = useRef(false);
  useEffect(() => {
    if (!autoRan.current && start.kind === "google_sheet" && start.url) {
      autoRan.current = true;
      runPreview.mutate();
    }
  }, [start, runPreview]);

  const save = useMutation({
    mutationFn: () => {
      if (kind === "google_sheet") return api<Source>("/products/sheet", { method: "PUT", json: { url: url.trim(), column_mapping: mapping } });
      const form = new FormData();
      form.append("file", file!);
      form.append("column_mapping", JSON.stringify(mapping));
      return api<Source>("/products/file", { method: "POST", form });
    },
    onSuccess: (src) => {
      toast.success(t.products.connectedToast(f.num(src.product_count ?? 0)));
      qc.setQueryData(keys.source, src);
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: keys.dashboard });
      onDone();
    },
  });

  const canPreview = kind === "google_sheet" ? url.trim().length > 10 : file !== null;
  const steps = [t.products.step1, t.products.step2, t.products.step3];

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4 sm:px-6">
        <ol className="flex items-center gap-2 sm:gap-3">
          {steps.map((label, i) => {
            const n = (i + 1) as 1 | 2 | 3;
            return (
              <li key={label} className="flex items-center gap-2 sm:gap-3" aria-current={n === step ? "step" : undefined}>
                {i > 0 && <span aria-hidden className={cx("h-0.5 w-5 rounded-full sm:w-8", n <= step ? "bg-brand-300" : "bg-slate-200")} />}
                <span
                  className={cx(
                    "num flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold transition-colors duration-300",
                    n < step ? "bg-emerald-500 text-white" : n === step ? "bg-brand-600 text-white ring-4 ring-brand-100" : "bg-surface text-slate-400 ring-2 ring-slate-200",
                  )}
                >
                  {n < step ? <Check className="size-4" strokeWidth={3} aria-hidden /> : f.num(n)}
                </span>
                <span className={cx("text-sm", n === step ? "font-semibold text-ink-950" : "text-slate-500 max-sm:hidden")}>{label}</span>
              </li>
            );
          })}
        </ol>
        {onCancel && (
          <Button variant="ghost" size="sm" onClick={onCancel}>
            {t.products.cancelWizard}
          </Button>
        )}
      </div>

      <div className="p-5 sm:p-6">
        {step === 1 && (
          <div className="animate-pop-in space-y-6">
            <fieldset>
              <legend className="sr-only">{t.products.step1}</legend>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <SourceOption
                  selected={kind === "google_sheet"}
                  onSelect={() => setKind("google_sheet")}
                  icon={<Sheet />}
                  title={t.products.sheetTitle}
                  badge={t.products.sheetRecommended}
                  desc={t.products.sheetDesc}
                />
                <SourceOption
                  selected={kind === "upload"}
                  onSelect={() => setKind("upload")}
                  icon={<FileSpreadsheet />}
                  title={t.products.fileTitle}
                  desc={t.products.fileDesc}
                />
              </div>
            </fieldset>

            {kind === "google_sheet" ? (
              <div className="space-y-3">
                <Field label={t.products.sheetUrl}>
                  {(id) => (
                    <Input
                      id={id}
                      dir="ltr"
                      type="url"
                      placeholder="https://docs.google.com/spreadsheets/d/..."
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                    />
                  )}
                </Field>
                <div className="flex gap-3 rounded-xl bg-brand-50/60 p-4 text-sm ring-1 ring-brand-100">
                  <Info className="mt-0.5 size-4 shrink-0 text-brand-500" aria-hidden />
                  <div className="min-w-0">
                    <div className="font-semibold text-ink-900">{t.products.sheetGuideTitle}</div>
                    <div className="ltr mt-1.5 text-xs leading-6 text-slate-600">
                      Share → General access → <b className="text-ink-900">Anyone with the link</b> → Viewer → Copy link
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-3 rounded-xl border-2 border-dashed border-slate-200 p-4">
                <input
                  ref={fileInput}
                  type="file"
                  className="hidden"
                  accept=".xlsx,.xls,.csv"
                  onChange={(e) => {
                    setFile(e.target.files?.[0] ?? null);
                    runPreview.reset();
                  }}
                />
                <Button variant="secondary" icon={<Upload className="size-4" />} onClick={() => fileInput.current?.click()}>
                  {t.products.chooseFile}
                </Button>
                <span className="min-w-0 text-sm text-slate-600" dir="auto">
                  {file ? t.products.fileChosen(file.name) : ".xlsx · .xls · .csv"}
                </span>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-slate-500">
              <span>{t.products.templateHint}</span>
              {/* no login needed, so a plain link works */}
              <a href={apiUrl("/products/template.csv")} className="inline-flex items-center gap-1 font-semibold text-brand-700 hover:underline" download>
                <Download className="size-4" aria-hidden />
                {t.products.template}
              </a>
            </div>

            {runPreview.error && <Alert kind="error">{errorMessage(runPreview.error, t)}</Alert>}

            <Footer>
              <span />
              <Button onClick={() => runPreview.mutate()} loading={runPreview.isPending} disabled={!canPreview}>
                {runPreview.isPending ? t.products.previewing : t.products.preview}
              </Button>
            </Footer>
          </div>
        )}

        {step === 2 && preview && (
          <div className="animate-pop-in space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-slate-500">{t.products.previewHint}</p>
              <Badge tone="brand">{t.products.rowCount(f.num(preview.row_count))}</Badge>
            </div>
            <div className="overflow-x-auto rounded-xl ring-1 ring-slate-200">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs text-slate-500">
                  <tr>
                    {preview.headers.map((h) => (
                      <th key={h} className="whitespace-nowrap px-4 py-3 text-start font-semibold">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {preview.sample_rows.map((row, i) => (
                    <tr key={i}>
                      {preview.headers.map((h) => (
                        <td key={h} className="num whitespace-nowrap px-4 py-3 text-ink-800">
                          {String((row as Record<string, unknown>)[h] ?? "")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Footer>
              <Button variant="secondary" onClick={() => setStep(1)}>
                {t.common.back}
              </Button>
              <Button onClick={() => setStep(3)}>{t.common.next}</Button>
            </Footer>
          </div>
        )}

        {step === 3 && preview && (
          <div className="animate-pop-in space-y-5">
            <p className="text-sm leading-6 text-slate-600">{t.products.mappingHint}</p>
            {fields.isPending ? (
              <PageLoading />
            ) : fields.error ? (
              <Alert kind="error">{errorMessage(fields.error, t)}</Alert>
            ) : (
              <MappingForm fields={fields.data} headers={preview.headers} mapping={mapping} onChange={setMapping} />
            )}
            <Alert kind="info">{t.products.mappingExtra}</Alert>
            {save.error && <Alert kind="error">{errorMessage(save.error, t)}</Alert>}
            <Footer>
              <Button variant="secondary" onClick={() => setStep(2)}>
                {t.common.back}
              </Button>
              <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!mapping.name}>
                {t.products.saveConnect}
              </Button>
            </Footer>
          </div>
        )}
      </div>
    </Card>
  );
}

function Footer({ children }: { children: ReactNode }) {
  return <div className="flex items-center justify-between gap-3 border-t border-slate-100 pt-5">{children}</div>;
}

/** A radio card: the whole card is the choice, with a check in the corner when selected. */
function SourceOption({
  selected,
  onSelect,
  icon,
  title,
  badge,
  desc,
}: {
  selected: boolean;
  onSelect: () => void;
  icon: ReactNode;
  title: string;
  badge?: string;
  desc: string;
}) {
  return (
    <label
      className={cx(
        "relative flex cursor-pointer items-start gap-3.5 rounded-2xl p-4 transition-[box-shadow,background-color] duration-200 has-focus-visible:outline-2 has-focus-visible:outline-brand-500",
        selected ? "bg-brand-50/60 ring-2 ring-brand-500" : "bg-surface ring-1 ring-slate-200 hover:ring-brand-300",
      )}
    >
      <input type="radio" name="product-source" checked={selected} onChange={onSelect} className="sr-only" />
      <span
        aria-hidden
        className={cx(
          "flex size-10 shrink-0 items-center justify-center rounded-xl [&>svg]:size-5",
          selected ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-500",
        )}
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2 font-semibold text-ink-950">
          {title}
          {badge && <Badge tone="green">{badge}</Badge>}
        </span>
        <span className="mt-1 block text-sm leading-6 text-slate-500">{desc}</span>
      </span>
      <span
        aria-hidden
        className={cx(
          "flex size-5 shrink-0 items-center justify-center rounded-full transition-colors",
          selected ? "bg-brand-600 text-white" : "ring-2 ring-slate-200",
        )}
      >
        {selected && <Check className="size-3" strokeWidth={3.5} />}
      </span>
    </label>
  );
}

function MappingForm({ fields, headers, mapping, onChange }: { fields: ProductField[]; headers: string[]; mapping: Mapping; onChange: (m: Mapping) => void }) {
  const { t, lang } = useI18n();
  const used = new Set(Object.values(mapping));

  function set(field: string, column: string) {
    const next = { ...mapping };
    if (column) next[field] = column;
    else delete next[field];
    onChange(next);
  }

  return (
    <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
      {fields.map((fld) => {
        const label = FIELD_LABELS[lang][fld.key] ?? fld.label;
        return (
          <Field
            key={fld.key}
            label={
              <>
                {label}
                {fld.required && <span className="ms-1 text-xs font-medium text-red-500">({t.products.required})</span>}
              </>
            }
          >
            {(id) => (
              <Select id={id} value={mapping[fld.key] ?? ""} onChange={(e) => set(fld.key, e.target.value)}>
                <option value="">{t.products.none}</option>
                {headers.map((h) => (
                  // each column can be used by only one field
                  <option key={h} value={h} disabled={used.has(h) && mapping[fld.key] !== h}>
                    {h}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        );
      })}
    </div>
  );
}
