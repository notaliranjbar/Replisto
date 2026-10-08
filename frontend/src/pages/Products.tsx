import { useEffect, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileSpreadsheet, Lock, Minus, Package, Pencil, Plus, RefreshCw, Search, Sheet, Trash2, Upload } from "lucide-react";
import { api } from "../api/client";
import { keys, useMe } from "../api/queries";
import type { Product, ProductIn, ProductOrigin, ProductPage, ProductSummary, Source } from "../api/types";
import ProductWizard, { type WizardStart } from "../components/ProductWizard";
import { PendingProposals, TeachBox } from "../components/teach";
import { useToast } from "../components/toast";
import { Alert, Badge, Button, Card, ConfirmDialog, EmptyState, Field, Input, Modal, PageHeader, PageLoading, Select, Textarea, cx } from "../components/ui";
import { useI18n } from "../i18n";
import { errorMessage } from "../lib/errors";

export default function Products() {
  const { t } = useI18n();
  const C = t.launch.catalogue;
  const source = useQuery({ queryKey: keys.source, queryFn: () => api<Source>("/products/source") });
  const [wizard, setWizard] = useState<WizardStart | null>(null);
  const [editing, setEditing] = useState<Product | "new" | null>(null);

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Package />}
        title={C.title}
        subtitle={C.subtitle}
        action={
          <>
            <Button icon={<Plus className="size-4" />} onClick={() => setEditing("new")}>
              {C.add}
            </Button>
            {!source.data?.connected && wizard === null && (
              <Button variant="secondary" icon={<Sheet className="size-4" />} onClick={() => setWizard({})}>
                {C.connectSheet}
              </Button>
            )}
          </>
        }
      />
      {source.error && <Alert kind="error">{errorMessage(source.error, t)}</Alert>}
      {wizard !== null ? (
        <ProductWizard start={wizard} onCancel={() => setWizard(null)} onDone={() => setWizard(null)} />
      ) : (
        <>
          <TeachBox />
          <PendingProposals />
          {source.data?.connected && (
            <SourceStatus
              source={source.data}
              onChangeColumns={() => setWizard({ kind: "google_sheet", url: source.data.url ?? "", mapping: source.data.column_mapping })}
              onReupload={() => setWizard({ kind: "upload", mapping: source.data.column_mapping })}
            />
          )}
          <Catalogue onEdit={setEditing} />
        </>
      )}
      <ProductModal product={editing} onClose={() => setEditing(null)} />
    </div>
  );
}

/** Where the products come from, how many there are, and the source's actions. */
function SourceStatus({ source, onChangeColumns, onReupload }: { source: Source; onChangeColumns: () => void; onReupload: () => void }) {
  const { t, f } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const isSheet = source.kind === "google_sheet";

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["products"] });
    qc.invalidateQueries({ queryKey: keys.dashboard });
  };

  const sync = useMutation({
    mutationFn: () => api<Source>("/products/sync", { method: "POST" }),
    onSuccess: () => {
      toast.success(t.products.synced);
      invalidate();
    },
    onError: (err) => {
      toast.error(errorMessage(err, t));
      invalidate();
    },
  });

  const disconnect = useMutation({
    mutationFn: () => api("/products/source", { method: "DELETE" }),
    onSuccess: () => {
      setConfirm(false);
      invalidate();
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  return (
    <Card className="animate-pop-in">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-5 p-5 sm:p-6">
        {/* real minimum width: on phones the numbers wrap below instead of squeezing this */}
        <div className="flex min-w-56 flex-1 items-center gap-4">
          <span aria-hidden className={cx("flex size-12 shrink-0 items-center justify-center rounded-2xl", isSheet ? "bg-emerald-50 text-emerald-600" : "bg-brand-50 text-brand-700")}>
            {isSheet ? <Sheet className="size-6" /> : <FileSpreadsheet className="size-6" />}
          </span>
          <div className="min-w-0">
            <div className="text-xs font-semibold text-slate-500">{t.products.statusTitle}</div>
            <div className="mt-0.5 font-bold text-ink-950">{isSheet ? t.products.kindSheet : t.products.kindFile}</div>
            {isSheet && source.url && (
              <a href={source.url} target="_blank" rel="noopener noreferrer" className="mt-0.5 inline-flex items-center gap-1 text-sm font-semibold text-brand-700 hover:underline">
                {t.products.openSheet}
                <ExternalLink className="size-3.5" aria-hidden />
              </a>
            )}
          </div>
        </div>

        <dl className="flex gap-8">
          <div>
            <dt className="text-xs font-semibold text-slate-500">{t.products.productCount}</dt>
            <dd className="num mt-0.5 text-2xl font-extrabold text-ink-950">{f.num(source.product_count ?? 0)}</dd>
          </div>
          {source.last_synced_at && (
            <div>
              <dt className="text-xs font-semibold text-slate-500">{t.products.lastSync}</dt>
              <dd className="mt-1.5 text-sm font-bold text-ink-900" title={f.dateTime(source.last_synced_at)}>
                {f.ago(source.last_synced_at)}
              </dd>
            </div>
          )}
        </dl>
      </div>

      {source.last_error && (
        <div className="px-5 pb-5 sm:px-6">
          <Alert kind="warning">
            {source.last_error}
            <div className="mt-1 text-xs opacity-80">{t.products.lastErrorNote}</div>
          </Alert>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 bg-slate-50/60 px-5 py-3 sm:px-6">
        {isSheet && (
          <Button variant="secondary" size="sm" icon={<RefreshCw className={cx("size-4", sync.isPending && "animate-spin")} />} disabled={sync.isPending} onClick={() => sync.mutate()}>
            {t.products.syncNow}
          </Button>
        )}
        {isSheet ? (
          <Button variant="secondary" size="sm" onClick={onChangeColumns}>
            {t.products.changeColumns}
          </Button>
        ) : (
          <Button variant="secondary" size="sm" icon={<Upload className="size-4" />} onClick={onReupload}>
            {t.products.reupload}
          </Button>
        )}
        <Button variant="ghost" size="sm" className="sm:ms-auto" onClick={() => setConfirm(true)}>
          <span className="text-red-700">{t.products.disconnect}</span>
        </Button>
      </div>
      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        onConfirm={() => disconnect.mutate()}
        loading={disconnect.isPending}
        danger
        title={t.products.disconnectConfirmTitle}
        body={t.products.disconnectConfirmBody}
        confirmLabel={t.products.disconnect}
        cancelLabel={t.common.cancel}
      />
    </Card>
  );
}


const PAGE = 50;
type StockFilter = "" | "in_stock" | "out_of_stock" | "unknown";

function useProductMutations() {
  const { t } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["products"] });
    qc.invalidateQueries({ queryKey: keys.dashboard });
  };
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ProductIn> }) => api<Product>(`/products/${id}`, { method: "PATCH", json: body }),
    onSuccess: invalidate,
    onError: (err) => toast.error(errorMessage(err, t)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/products/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success(t.launch.catalogue.deleted);
      invalidate();
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });
  return { patch, remove };
}

function Catalogue({ onEdit }: { onEdit: (p: Product) => void }) {
  const { t, f } = useI18n();
  const currency = useMe().data?.shop.currency ?? "USD";
  const C = t.launch.catalogue;
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [stock, setStock] = useState<StockFilter>("");
  const [origin, setOrigin] = useState<ProductOrigin | "">("");
  const [deleting, setDeleting] = useState<Product | null>(null);
  const { patch, remove } = useProductMutations();

  useEffect(() => {
    const id = setTimeout(() => {
      setSearch(q.trim());
      setOffset(0);
    }, 300);
    return () => clearTimeout(id);
  }, [q]);

  const summary = useQuery({ queryKey: keys.productSummary, queryFn: () => api<ProductSummary>("/products/summary") });
  const { data, isPending, error, isFetching } = useQuery({
    queryKey: keys.products(search, offset, origin, stock),
    queryFn: () => api<ProductPage>("/products", { query: { q: search, offset, limit: PAGE, origin, stock } }),
    placeholderData: keepPreviousData,
  });

  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE)) : 1;
  const page = Math.floor(offset / PAGE) + 1;
  const origins = Object.entries(summary.data?.by_origin ?? {});
  const filterBtn = (value: StockFilter, label: string) => (
    <Button
      size="sm"
      variant={stock === value ? "primary" : "ghost"}
      onClick={() => {
        setStock(value);
        setOffset(0);
      }}
    >
      {label}
    </Button>
  );

  return (
    <Card>
      <div className="space-y-3 border-b border-slate-100 px-5 py-4 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-bold text-ink-950">{C.title}</h2>
            {summary.data && (
              <p className="num mt-0.5 text-sm text-slate-500">
                {C.summary(f.num(summary.data.total), f.num(summary.data.in_stock), f.num(summary.data.out_of_stock))}
              </p>
            )}
          </div>
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute start-3.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <Input className="ps-10" placeholder={t.products.searchPlaceholder} aria-label={t.products.searchPlaceholder} value={q} onChange={(e) => setQ(e.target.value)} maxLength={100} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {filterBtn("", C.filterAll)}
          {filterBtn("in_stock", C.filterInStock)}
          {filterBtn("out_of_stock", C.filterOut)}
          {filterBtn("unknown", C.filterUnknown)}
          {origins.length > 1 && (
            <Select
              className="ms-auto h-9 w-auto min-w-40"
              aria-label={C.allOrigins}
              value={origin}
              onChange={(e) => {
                setOrigin(e.target.value as ProductOrigin | "");
                setOffset(0);
              }}
            >
              <option value="">{C.allOrigins}</option>
              {origins.map(([key, n]) => (
                <option key={key} value={key}>
                  {`${C.origins[key] ?? key} (${f.num(n)})`}
                </option>
              ))}
            </Select>
          )}
        </div>
      </div>

      {isPending ? (
        <PageLoading />
      ) : error ? (
        <div className="p-5">
          <Alert kind="error">{errorMessage(error, t)}</Alert>
        </div>
      ) : data.items.length === 0 ? (
        <EmptyState icon={<Package />} title={search || stock || origin ? t.common.noResults : C.empty} />
      ) : (
        <div className={cx("transition-opacity", isFetching && "opacity-60")}>
          <ul className="divide-y divide-slate-100">
            {data.items.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-x-1 gap-y-2 px-5 py-3.5 transition-colors hover:bg-brand-50/30 sm:gap-x-4 sm:px-6">
                <button type="button" onClick={() => onEdit(p)} className="min-w-48 flex-1 basis-full text-start sm:basis-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-bold text-ink-950" dir="auto">
                      {p.name}
                    </span>
                    <Badge tone={p.origin === "sheet" ? "green" : p.origin === "manual" ? "neutral" : "brand"}>
                      {!p.editable && <Lock aria-hidden />}
                      {C.origins[p.origin] ?? p.origin}
                    </Badge>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1.5 text-xs text-slate-500">
                    {[p.category, p.color, p.size, p.sku].filter(Boolean).map((v) => (
                      <span key={String(v)} className="num rounded-md bg-slate-100 px-1.5 py-0.5">
                        {v}
                      </span>
                    ))}
                  </div>
                </button>
                {/* phones: price, stock and actions share one row under the name */}
                <div className="num me-auto text-sm font-bold text-ink-950 sm:me-0 sm:w-32 sm:text-end">{p.price != null ? f.money(p.price, currency) : "—"}</div>
                <div className="flex items-center justify-end gap-1 sm:w-36">
                  {p.editable && (
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={C.stockMinus}
                      title={C.stockMinus}
                      disabled={!p.stock || patch.isPending}
                      onClick={() => patch.mutate({ id: p.id, body: { stock: Math.max(0, (p.stock ?? 0) - 1) } })}
                    >
                      <Minus className="size-3.5" />
                    </Button>
                  )}
                  <Stock p={p} />
                  {p.editable && (
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={C.stockPlus}
                      title={C.stockPlus}
                      disabled={patch.isPending}
                      onClick={() => patch.mutate({ id: p.id, body: { stock: (p.stock ?? 0) + 1 } })}
                    >
                      <Plus className="size-3.5" />
                    </Button>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <Button size="sm" variant="ghost" aria-label={t.common.edit} title={p.editable ? t.common.edit : C.sheetLocked} onClick={() => onEdit(p)}>
                    <Pencil className="size-4" />
                  </Button>
                  {p.editable && (
                    <Button size="sm" variant="ghost" aria-label={t.common.delete} onClick={() => setDeleting(p)}>
                      <Trash2 className="size-4 text-red-600" />
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>

          {pages > 1 && (
            <div className="flex items-center justify-between gap-3 border-t border-slate-100 px-5 py-3 text-sm sm:px-6">
              <Button size="sm" variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                {t.products.prev}
              </Button>
              <span className="num font-medium text-slate-500">{t.products.pageOf(f.num(page), f.num(pages))}</span>
              <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => setOffset(offset + PAGE)}>
                {t.products.nextPage}
              </Button>
            </div>
          )}
        </div>
      )}
      <ConfirmDialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        onConfirm={() => {
          if (deleting) remove.mutate(deleting.id);
          setDeleting(null);
        }}
        danger
        title={t.common.delete}
        body={deleting ? C.deleteConfirm(deleting.name) : ""}
        confirmLabel={t.common.delete}
        cancelLabel={t.common.cancel}
      />
    </Card>
  );
}

function Stock({ p }: { p: Product }) {
  const { t, f } = useI18n();
  if (p.stock == null) return <span className="px-1 text-xs text-slate-400">{t.products.stockUnknown}</span>;
  if (p.stock === 0) return <Badge tone="red">{t.products.outOfStock}</Badge>;
  return <span className="num min-w-6 text-center text-sm font-semibold text-emerald-700">{f.num(p.stock)}</span>;
}

type FormKey = "name" | "sku" | "category" | "color" | "size" | "price" | "stock" | "description" | "image_url" | "post_url";
type FormState = Record<FormKey, string>;
const EMPTY: FormState = { name: "", sku: "", category: "", color: "", size: "", price: "", stock: "", description: "", image_url: "", post_url: "" };

function toForm(p: Product): FormState {
  const v = (x: unknown) => (x === null || x === undefined ? "" : String(x));
  return {
    name: p.name,
    sku: v(p.sku),
    category: v(p.category),
    color: v(p.color),
    size: v(p.size),
    price: v(p.price),
    stock: v(p.stock),
    description: v(p.description),
    image_url: v(p.image_url),
    post_url: v(p.post_url),
  };
}

const ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";

/** Arabic-Indic digits and the Arabic decimal separator → ASCII. */
function asciiNumber(s: string): string {
  return Array.from(s)
    .map((c) => (ARABIC_DIGITS.includes(c) ? String(ARABIC_DIGITS.indexOf(c)) : c === "٫" ? "." : c))
    .join("");
}

/** "١٢" → 12; empty → null. */
function digits(s: string): number | null {
  const d = asciiNumber(s).replace(/[^\d]/g, "");
  return d === "" ? null : Number(d);
}

/** "$1,250.50" → 1250.5; empty → null. */
function amount(s: string): number | null {
  const d = asciiNumber(s).replace(/[^\d.]/g, "");
  if (d === "" || d === ".") return null;
  const v = Number(d);
  return Number.isFinite(v) ? Math.round(v * 100) / 100 : null;
}

function ProductModal({ product, onClose }: { product: Product | "new" | null; onClose: () => void }) {
  const { t, f } = useI18n();
  const C = t.launch.catalogue;
  const toast = useToast();
  const qc = useQueryClient();
  const [form, setForm] = useState<FormState>(EMPTY);
  const editing = product && product !== "new" ? product : null;
  const locked = editing ? !editing.editable : false;
  const currency = useMe().data?.shop.currency ?? "USD";

  useEffect(() => {
    setForm(product && product !== "new" ? toForm(product) : EMPTY);
  }, [product]);

  const save = useMutation({
    mutationFn: () => {
      const body = {
        name: form.name.trim(),
        sku: form.sku.trim() || null,
        category: form.category.trim() || null,
        color: form.color.trim() || null,
        size: form.size.trim() || null,
        price: amount(form.price),
        stock: digits(form.stock),
        description: form.description.trim() || null,
        image_url: form.image_url.trim() || null,
        post_url: form.post_url.trim() || null,
      };
      return editing ? api<Product>(`/products/${editing.id}`, { method: "PATCH", json: body }) : api<Product>("/products", { method: "POST", json: body });
    },
    onSuccess: () => {
      toast.success(C.saved);
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: keys.dashboard });
      onClose();
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  const field = (key: FormKey, label: string, opts: { ltr?: boolean; numeric?: boolean; decimal?: boolean; hint?: string } = {}) => (
    <Field label={label} hint={opts.hint}>
      {(id) => (
        <Input
          id={id}
          value={form[key]}
          dir={opts.ltr ? "ltr" : "auto"}
          inputMode={opts.numeric ? "numeric" : opts.decimal ? "decimal" : undefined}
          disabled={locked}
          onChange={(e) => setForm({ ...form, [key]: e.target.value })}
          data-autofocus={key === "name" ? true : undefined}
        />
      )}
    </Field>
  );

  const knows = editing ? Object.entries(editing.bot_view ?? {}) : [];

  return (
    <Modal
      open={product !== null}
      onClose={onClose}
      size="lg"
      title={editing ? C.editTitle : C.addTitle}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t.common.cancel}
          </Button>
          {!locked && (
            <Button loading={save.isPending} disabled={!form.name.trim()} onClick={() => save.mutate()}>
              {t.common.save}
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-4">
        {locked && <Alert kind="info">{C.sheetLocked}</Alert>}
        {field("name", C.name)}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {field("price", `${C.price} (${currency})`, { decimal: true, ltr: true })}
          {field("stock", C.stock, { numeric: true, ltr: true, hint: C.stockHint })}
          {field("color", C.color)}
          {field("size", C.size)}
          {field("category", C.category)}
          {field("sku", C.sku, { ltr: true })}
        </div>
        <Field label={C.description}>
          {(id) => <Textarea id={id} rows={3} value={form.description} disabled={locked} onChange={(e) => setForm({ ...form, description: e.target.value })} />}
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {field("image_url", C.imageUrl, { ltr: true })}
          {field("post_url", C.postUrl, { ltr: true })}
        </div>
        {knows.length > 0 && (
          <div className="rounded-xl bg-brand-50/60 p-4 ring-1 ring-brand-100">
            <div className="mb-2 text-xs font-bold text-brand-800">{C.botKnows}</div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              {knows.map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-slate-500">{C.botFields[k] ?? k}</dt>
                  <dd className="num text-ink-900" dir="auto">
                    {typeof v === "number" ? f.num(v) : typeof v === "boolean" ? (v ? t.common.yes : t.common.no) : typeof v === "object" ? JSON.stringify(v) : String(v)}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </div>
    </Modal>
  );
}
