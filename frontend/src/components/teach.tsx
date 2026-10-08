import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Link2, Lock, RefreshCw, Sparkles, Type, Undo2 } from "lucide-react";
import { api } from "../api/client";
import { keys, useSections } from "../api/queries";
import type { Proposal, ProposalChanges, ProposalPage, ProposedProduct } from "../api/types";
import { useI18n } from "../i18n";
import { localizeSection } from "../i18n/sections";
import { errorMessage } from "../lib/errors";
import { useToast } from "./toast";
import { Alert, Badge, Button, Card, Input, Tabs, Textarea, cx } from "./ui";

type Mode = "text" | "link" | "file";

/** Products and shop info changed: everything that shows them must refresh. */
function useInvalidateCatalogue() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["products"] });
    qc.invalidateQueries({ queryKey: keys.proposals });
    qc.invalidateQueries({ queryKey: keys.knowledge });
    qc.invalidateQueries({ queryKey: keys.dashboard });
    qc.invalidateQueries({ queryKey: keys.billing });
  };
}

/** "Describe it any way you like": text, a Google link or a file → a proposal to confirm. */
export function TeachBox() {
  const { t } = useI18n();
  const T = t.launch.teach;
  const toast = useToast();
  const qc = useQueryClient();
  const [mode, setMode] = useState<Mode>("text");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const send = useMutation({
    mutationFn: () => {
      if (mode === "text") return api<Proposal>("/teach/text", { method: "POST", json: { text } });
      if (mode === "link") return api<Proposal>("/teach/url", { method: "POST", json: { url: url.trim() } });
      const form = new FormData();
      form.append("file", file as File);
      return api<Proposal>("/teach/file", { method: "POST", form });
    },
    onSuccess: () => {
      setText("");
      setUrl("");
      setFile(null);
      qc.invalidateQueries({ queryKey: keys.proposals });
      qc.invalidateQueries({ queryKey: keys.billing });
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  const ready = mode === "text" ? text.trim().length > 2 : mode === "link" ? url.trim().length > 10 : file !== null;

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-start gap-3 border-b border-slate-100 px-5 py-4 sm:px-6">
        <span aria-hidden className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white shadow-md shadow-brand-600/25">
          <Sparkles className="size-[18px]" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="font-bold text-ink-950">{T.title}</h2>
          <p className="mt-0.5 text-sm leading-6 text-slate-500">{T.subtitle}</p>
        </div>
      </div>
      <form
        className="space-y-4 p-5 sm:px-6"
        onSubmit={(e) => {
          e.preventDefault();
          if (ready) send.mutate();
        }}
      >
        <Tabs
          value={mode}
          onChange={setMode}
          items={[
            { value: "text", label: <><Type className="size-4" aria-hidden /> {T.tabText}</> },
            { value: "link", label: <><Link2 className="size-4" aria-hidden /> {T.tabLink}</> },
            { value: "file", label: <><FileUp className="size-4" aria-hidden /> {T.tabFile}</> },
          ]}
        />
        {mode === "text" && (
          <Textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder={T.textPlaceholder} aria-label={T.tabText} maxLength={60000} />
        )}
        {mode === "link" && (
          <div>
            <Input dir="ltr" value={url} onChange={(e) => setUrl(e.target.value)} placeholder={T.linkPlaceholder} aria-label={T.tabLink} />
            <p className="mt-1.5 text-xs leading-5 text-slate-500">{T.linkHint}</p>
          </div>
        )}
        {mode === "file" && (
          <div className="flex flex-wrap items-center gap-3">
            <input
              ref={fileRef}
              type="file"
              className="hidden"
              accept=".pdf,.docx,.xlsx,.csv,.txt,.md,.jpg,.jpeg,.png,.webp"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <Button variant="secondary" icon={<FileUp className="size-4" />} onClick={() => fileRef.current?.click()}>
              {T.chooseFile}
            </Button>
            <span className="min-w-0 truncate text-sm text-slate-600">{file ? file.name : T.fileHint}</span>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" icon={<Sparkles className="size-4" />} loading={send.isPending} disabled={!ready}>
            {send.isPending ? T.thinking : T.understand}
          </Button>
        </div>
      </form>
    </Card>
  );
}

/** Proposals waiting for the owner's OK. */
export function PendingProposals() {
  const { t } = useI18n();
  const pending = useQuery({
    queryKey: [...keys.proposals, "pending"],
    queryFn: () => api<ProposalPage>("/teach/proposals", { query: { status: "pending", limit: 20 } }),
    refetchInterval: 15_000,
  });
  if (!pending.data?.items.length) return null;
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-bold text-slate-500">{t.launch.teach.pendingTitle}</h2>
      {pending.data.items.map((p) => (
        <ProposalCard key={p.id} proposal={p} />
      ))}
    </section>
  );
}

export function ProposalCard({ proposal }: { proposal: Proposal }) {
  const { t, f, lang } = useI18n();
  const sections = useSections();
  const sectionLabel = (key: string) => {
    const s = sections.data?.sections.find((x) => x.key === key);
    return s ? localizeSection(s, lang).label : key;
  };
  const T = t.launch.teach;
  const toast = useToast();
  const invalidate = useInvalidateCatalogue();
  const changes = proposal.changes as ProposalChanges;
  const products = changes.products ?? [];
  const knowledge = changes.knowledge ?? [];
  const [skipP, setSkipP] = useState<Set<number>>(new Set());
  const [skipK, setSkipK] = useState<Set<number>>(new Set());

  const apply = useMutation({
    mutationFn: () =>
      api<Proposal>(`/teach/proposals/${proposal.id}/apply`, {
        method: "POST",
        json: { skip_products: [...skipP], skip_knowledge: [...skipK] },
      }),
    onSuccess: (p) => {
      toast.success(p.result || T.applied);
      invalidate();
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });
  const discard = useMutation({
    mutationFn: () => api<Proposal>(`/teach/proposals/${proposal.id}/discard`, { method: "POST" }),
    onSuccess: () => {
      toast.success(T.discarded);
      invalidate();
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  const toggle = (set: Set<number>, setter: (s: Set<number>) => void, i: number) => {
    const next = new Set(set);
    if (next.has(i)) next.delete(i);
    else next.add(i);
    setter(next);
  };
  const selectable = products.filter((p) => !p.locked).length + knowledge.length;
  const selected = selectable - [...skipP].filter((i) => !products[i]?.locked).length - skipK.size;
  const empty = !products.length && !knowledge.length && !changes.sheet;

  return (
    <Card className="animate-pop-in overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-5 py-3 sm:px-6">
        <Badge tone="brand">{T.proposalFrom[proposal.source] ?? proposal.source}</Badge>
        <span className="min-w-0 flex-1 truncate text-xs text-slate-500" dir="auto">
          {proposal.source_label}
        </span>
        <span className="text-xs text-slate-400">{f.smart(proposal.created_at)}</span>
      </div>
      <div className="space-y-4 p-5 sm:px-6">
        {proposal.summary && <p className="user-text text-sm leading-7 text-ink-900">{proposal.summary}</p>}

        {products.length > 0 && (
          <ul className="divide-y divide-slate-100 overflow-hidden rounded-xl ring-1 ring-line">
            {products.map((p, i) => (
              <ProductRow key={i} change={p} checked={!skipP.has(i)} onToggle={() => toggle(skipP, setSkipP, i)} />
            ))}
          </ul>
        )}

        {knowledge.length > 0 && (
          <ul className="space-y-2">
            {knowledge.map((k, i) => (
              <li key={i} className="flex items-start gap-3 rounded-xl bg-fill px-3.5 py-2.5">
                <input type="checkbox" className="mt-1.5 size-4 accent-brand-600" checked={!skipK.has(i)} onChange={() => toggle(skipK, setSkipK, i)} aria-label={k.title || k.section} />
                <div className="min-w-0 flex-1 text-sm">
                  <div className="font-semibold text-ink-900">
                    {sectionLabel(k.section)}
                    {k.title && <span className="font-normal text-slate-500"> · {k.title}</span>}
                    <span className="ms-2 text-xs font-medium text-brand-700">{k.mode === "replace" ? T.knowledgeReplace : T.knowledgeAdd}</span>
                  </div>
                  <p className="user-text mt-1 line-clamp-3 leading-6 text-slate-600">{k.content}</p>
                </div>
              </li>
            ))}
          </ul>
        )}

        {changes.sheet && (
          <div className="flex items-center gap-2 rounded-xl bg-emerald-50 px-3.5 py-2.5 text-sm font-semibold text-emerald-800 ring-1 ring-emerald-200">
            <RefreshCw className="size-4" aria-hidden />
            {T.sheet(f.num(changes.sheet.rows))}
          </div>
        )}

        {!!changes.questions?.length && (
          <Alert kind="warning">
            <div className="font-semibold">{T.questions}</div>
            <ul className="mt-1 list-disc space-y-0.5 ps-5">
              {changes.questions.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
            <div className="mt-1 text-xs opacity-80">{T.questionsHint}</div>
          </Alert>
        )}
        {empty && !changes.questions?.length && <p className="text-sm text-slate-500">{T.nothing}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 bg-slate-50/60 px-5 py-3 sm:px-6">
        {!empty && (
          <Button size="sm" loading={apply.isPending} onClick={() => apply.mutate()} disabled={!changes.sheet && selected <= 0}>
            {selected < selectable ? T.applySome(f.num(Math.max(selected, 0))) : T.apply}
          </Button>
        )}
        <Button size="sm" variant="ghost" loading={discard.isPending} onClick={() => discard.mutate()}>
          {T.discard}
        </Button>
      </div>
    </Card>
  );
}

function ProductRow({ change, checked, onToggle }: { change: ProposedProduct; checked: boolean; onToggle: () => void }) {
  const { t, f } = useI18n();
  const T = t.launch.teach;
  const before = (change.before ?? {}) as Record<string, unknown>;
  const fields = change.fields;
  const show = (key: string, v: unknown) => (v === null || v === undefined || v === "" ? "—" : key === "price" ? f.num(Number(v)) : String(v));
  const name = String(fields.name ?? before.name ?? "");
  const variant = [fields.color ?? before.color, fields.size ?? before.size].filter(Boolean).join(" · ");
  const tone = change.action === "create" ? "green" : change.action === "delete" ? "red" : "amber";

  return (
    <li className={cx("flex items-start gap-3 px-3.5 py-3", change.locked && "bg-slate-50")}>
      {change.locked ? (
        <Lock className="mt-1 size-4 shrink-0 text-slate-400" aria-label={T.lockedRow} />
      ) : (
        <input type="checkbox" className="mt-1.5 size-4 accent-brand-600" checked={checked} onChange={onToggle} aria-label={name} />
      )}
      <div className="min-w-0 flex-1 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={tone}>{T[change.action]}</Badge>
          <span className="font-bold text-ink-950" dir="auto">
            {name}
          </span>
          {variant && <span className="text-slate-500">{variant}</span>}
          {change.locked && <span className="text-xs text-slate-500">({T.lockedRow})</span>}
        </div>
        {change.action === "create" && (
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
            {"price" in fields && <span className="num">{T.fields.price}: {show("price", fields.price)}</span>}
            {"stock" in fields && <span className="num">{T.fields.stock}: {show("stock", fields.stock)}</span>}
            {"description" in fields && <span className="line-clamp-1">{String(fields.description)}</span>}
          </div>
        )}
        {change.action === "update" && (
          <ul className="mt-1 space-y-0.5 text-xs text-slate-600">
            {Object.entries(fields).map(([key, v]) => (
              <li key={key} className="num">
                {T.fields[key] ?? key}: <span className="text-slate-400 line-through">{show(key, before[key])}</span> ← <b className="text-ink-900">{show(key, v)}</b>
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}

/** Undo for an applied proposal (e.g. a channel post read as a product by mistake). */
export function UndoProposal({ id }: { id: string }) {
  const { t } = useI18n();
  const toast = useToast();
  const invalidate = useInvalidateCatalogue();
  const undo = useMutation({
    mutationFn: () => api(`/teach/proposals/${id}/undo`, { method: "POST" }),
    onSuccess: () => {
      toast.success(t.launch.teach.undone);
      invalidate();
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });
  return (
    <Button size="sm" variant="ghost" icon={<Undo2 className="size-4" />} loading={undo.isPending} onClick={() => undo.mutate()}>
      {t.launch.teach.undo}
    </Button>
  );
}
