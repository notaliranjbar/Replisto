import { useEffect, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  Check,
  CloudUpload,
  CreditCard,
  FileText,
  MessageCircleQuestionMark,
  NotebookPen,
  Phone,
  Plus,
  Store,
  Truck,
  Undo2,
} from "lucide-react";
import { api } from "../api/client";
import { keys, useSections } from "../api/queries";
import type { Entry, Knowledge as KnowledgeData, KnowledgeSection, Section } from "../api/types";
import { EntryCard, EntryEditor, useInvalidateKnowledge } from "../components/knowledge";
import { useToast } from "../components/toast";
import { Alert, Badge, Button, Card, CardHeader, PageHeader, PageLoading, ProgressBar, Spinner, Textarea, cx } from "../components/ui";
import { useI18n } from "../i18n";
import { localizeSection } from "../i18n/sections";
import { errorMessage } from "../lib/errors";
import { formatBytesMB } from "../lib/format";

const ICONS: Record<string, ReactNode> = {
  about: <Store />,
  shipping: <Truck />,
  payment: <CreditCard />,
  returns: <Undo2 />,
  contact: <Phone />,
  faq: <MessageCircleQuestionMark />,
  free_text: <NotebookPen />,
  file: <FileText />,
};
const anchor = (key: string) => `section-${key}`;

export default function Knowledge() {
  const { t, lang } = useI18n();
  const sections = useSections();
  const knowledge = useQuery({ queryKey: keys.knowledge, queryFn: () => api<KnowledgeData>("/knowledge") });

  const header = <PageHeader icon={<BookOpen />} title={t.knowledge.title} subtitle={t.knowledge.subtitle} />;
  if (sections.isPending || knowledge.isPending)
    return (
      <>
        {header}
        <PageLoading />
      </>
    );
  if (sections.error || knowledge.error)
    return (
      <>
        {header}
        <Alert kind="error">{errorMessage(sections.error ?? knowledge.error, t)}</Alert>
      </>
    );

  const bySection = (key: KnowledgeSection) => knowledge.data.entries.filter((e) => e.section === key);
  const list = sections.data.sections.map((raw) => localizeSection(raw, lang));

  return (
    <>
      {header}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-8">
        <aside className="min-w-0 space-y-4 lg:sticky lg:top-10 lg:self-start">
          <Usage used={knowledge.data.chars_used} limit={knowledge.data.char_limit} />
          <SectionNav sections={list} count={(key) => bySection(key).length} />
        </aside>

        <div className="min-w-0 space-y-6">
          {list.map((section) => {
            const entries = bySection(section.key);
            if (!section.multiple) return <SingleSection key={section.key} section={section} entry={entries[0]} />;
            if (section.key === "file")
              return (
                <FileSection
                  key={section.key}
                  section={section}
                  entries={entries}
                  types={sections.data.supported_file_types}
                  maxBytes={sections.data.max_file_bytes}
                />
              );
            return <MultiSection key={section.key} section={section} entries={entries} />;
          })}
        </div>
      </div>
    </>
  );
}

function Usage({ used, limit }: { used: number; limit: number }) {
  const { t, f } = useI18n();
  const full = used >= limit;
  const pct = Math.min(100, Math.round((used / Math.max(limit, 1)) * 100));
  return (
    <Card className="p-5">
      <div className="text-sm font-semibold text-slate-500">{t.knowledge.usage}</div>
      <div className="num mb-3 mt-1 text-2xl font-semibold tracking-tight text-ink-950">
        {f.num(pct)}
        %
      </div>
      <ProgressBar value={used} max={limit} />
      <div className="num mt-2 text-xs text-slate-500">
        {f.num(used)} / {f.num(limit)} {t.knowledge.chars}
      </div>
      {full && <p className="mt-3 text-xs font-medium leading-5 text-red-700">{t.knowledge.usageFull}</p>}
    </Card>
  );
}

/** Jump links to each section with a filled/empty marker: a rail on desktop, chips on phones. */
function SectionNav({ sections, count }: { sections: Section[]; count: (key: KnowledgeSection) => number }) {
  const { t, f } = useI18n();
  return (
    <nav aria-label={t.panel.knowledge.navTitle}>
      <div className="mb-2 hidden px-1 text-xs font-semibold text-slate-400 lg:block">{t.panel.knowledge.navTitle}</div>
      <ul className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 no-scrollbar sm:-mx-6 sm:px-6 lg:m-0 lg:flex-col lg:gap-0.5 lg:p-0">
        {sections.map((s) => {
          const n = count(s.key);
          return (
            <li key={s.key} className="shrink-0">
              <a
                href={`#${anchor(s.key)}`}
                className={cx(
                  "flex items-center gap-2.5 whitespace-nowrap rounded-xl text-sm font-semibold transition-colors",
                  "bg-surface px-3 py-2 shadow-sm ring-1 ring-line hover:text-brand-700",
                  "lg:bg-transparent lg:shadow-none lg:ring-0 lg:hover:bg-surface lg:hover:shadow-sm",
                  "[&>svg:first-child]:size-4 [&>svg:first-child]:shrink-0 [&>svg:first-child]:text-slate-400",
                  n > 0 ? "text-ink-900" : "text-slate-500",
                )}
              >
                {ICONS[s.key]}
                <span className="flex-1 truncate">{s.label}</span>
                {n > 0 &&
                  (s.multiple ? (
                    <span className="num rounded-full bg-brand-50 px-1.5 text-xs leading-5 text-brand-700">{f.num(n)}</span>
                  ) : (
                    <Check className="size-4 shrink-0 text-emerald-500" strokeWidth={3} aria-label={t.panel.knowledge.filled} />
                  ))}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function SectionCard({ section, children, action }: { section: Section; children: ReactNode; action?: ReactNode }) {
  return (
    <section id={anchor(section.key)} aria-label={section.label} className="scroll-mt-24 lg:scroll-mt-10">
      <Card>
        <CardHeader icon={ICONS[section.key]} title={section.label} subtitle={section.hint} action={action} />
        <div className="p-5 sm:p-6">{children}</div>
      </Card>
    </section>
  );
}

/** One text box per section: about, shipping, payment, returns, contact. */
function SingleSection({ section, entry }: { section: Section; entry: Entry | undefined }) {
  const { t, f } = useI18n();
  const toast = useToast();
  const invalidate = useInvalidateKnowledge();
  const saved = entry?.content ?? "";
  const [text, setText] = useState(saved);
  const dirty = text.trim() !== saved.trim();

  // pick up the server value when it changes and the user isn't mid-edit
  const lastSaved = useRef(saved);
  useEffect(() => {
    if (lastSaved.current !== saved) {
      lastSaved.current = saved;
      setText(saved);
    }
  }, [saved]);

  const save = useMutation({
    mutationFn: () => api<Entry | null>(`/knowledge/single/${section.key}`, { method: "PUT", json: { content: text } }),
    onSuccess: () => {
      toast.success(t.common.saved);
      invalidate();
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  return (
    <SectionCard
      section={section}
      action={
        saved ? (
          <Badge tone="green">
            <Check aria-hidden />
            {t.panel.knowledge.filled}
          </Badge>
        ) : (
          <Badge>{t.panel.knowledge.empty}</Badge>
        )
      }
    >
      <Textarea rows={4} value={text} placeholder={section.placeholder} onChange={(e) => setText(e.target.value)} aria-label={section.label} />
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <span className="text-xs text-slate-400">
          <span className="num">{f.num(text.length)}</span> {t.knowledge.chars}
          {dirty && saved && !text.trim() && <span className="ms-2 text-amber-600">· {t.knowledge.singleEmpty}</span>}
        </span>
        <div className="flex items-center gap-3">
          {dirty && (
            <span className="flex items-center gap-1.5 text-xs font-medium text-amber-600">
              <span className="size-1.5 rounded-full bg-amber-500" aria-hidden />
              {t.common.unsavedChanges}
            </span>
          )}
          <Button size="sm" onClick={() => save.mutate()} loading={save.isPending} disabled={!dirty}>
            {t.common.save}
          </Button>
        </div>
      </div>
    </SectionCard>
  );
}

/** List of cards: faq (question/answer) and free_text. */
function MultiSection({ section, entries }: { section: Section; entries: Entry[] }) {
  const { t } = useI18n();
  const [adding, setAdding] = useState(false);
  const isFaq = section.key === "faq";

  return (
    <SectionCard
      section={section}
      action={
        !adding && (
          <Button size="sm" variant="soft" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>
            {isFaq ? t.knowledge.addFaq : t.knowledge.addItem}
          </Button>
        )
      }
    >
      <div className="space-y-3">
        {adding && <EntryEditor section={section} onDone={() => setAdding(false)} />}
        {entries.map((e) => (
          <EntryCard key={e.id} section={section} entry={e} />
        ))}
        {!adding && entries.length === 0 && (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-200 py-6 text-sm font-semibold text-slate-500 transition-colors hover:border-brand-300 hover:text-brand-700"
          >
            <Plus className="size-4" aria-hidden />
            {isFaq ? t.knowledge.addFaq : t.knowledge.addItem}
          </button>
        )}
      </div>
    </SectionCard>
  );
}

function FileSection({ section, entries, types, maxBytes }: { section: Section; entries: Entry[]; types: string[]; maxBytes: number }) {
  const { t, f } = useI18n();
  const toast = useToast();
  const invalidate = useInvalidateKnowledge();
  const input = useRef<HTMLInputElement>(null);
  const [fresh, setFresh] = useState<string | null>(null);
  const [over, setOver] = useState(false);

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api<Entry>("/knowledge/upload", { method: "POST", form });
    },
    onSuccess: (entry) => {
      setFresh(entry.id);
      invalidate();
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  function pick(file: File | undefined) {
    if (input.current) input.current.value = "";
    if (!file || upload.isPending) return;
    const ext = "." + (file.name.split(".").pop() ?? "").toLowerCase();
    if (!types.includes(ext)) return toast.error(t.errors.fileType);
    if (file.size > maxBytes) return toast.error(t.errors.fileTooBig(f.num(formatBytesMB(maxBytes))));
    upload.mutate(file);
  }

  return (
    <SectionCard section={section}>
      <input ref={input} type="file" className="hidden" accept={types.join(",")} onChange={(e) => pick(e.target.files?.[0])} />
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          pick(e.dataTransfer.files?.[0]);
        }}
        className={cx(
          "flex flex-col items-center rounded-2xl border-2 border-dashed px-6 py-8 text-center transition-colors duration-200",
          over ? "border-brand-500 bg-brand-50" : "border-brand-200 bg-brand-50/40",
        )}
      >
        {upload.isPending ? (
          <>
            <Spinner className="size-8" />
            <p className="mt-3 max-w-sm text-sm font-medium text-ink-800">{t.knowledge.uploading}</p>
          </>
        ) : (
          <>
            <span aria-hidden className="flex size-12 items-center justify-center rounded-2xl bg-surface text-brand-700 shadow-sm ring-1 ring-brand-100">
              <CloudUpload className="size-6" />
            </span>
            <p className="mt-3 text-sm font-semibold text-ink-900">
              {t.panel.knowledge.drop} <span className="font-medium text-slate-500">{t.panel.knowledge.or}</span>
            </p>
            <Button size="sm" variant="secondary" className="mt-2" onClick={() => input.current?.click()}>
              {t.panel.knowledge.choose}
            </Button>
            <p className="mt-3 text-xs text-slate-500" dir="auto">
              {t.knowledge.uploadHint(types.join(" "), f.num(formatBytesMB(maxBytes)))}
            </p>
          </>
        )}
      </div>
      {entries.length > 0 && (
        <div className="mt-4 space-y-3">
          {entries.map((e) => (
            <EntryCard key={e.id} section={section} entry={e} startEditing={e.id === fresh} onEditEnd={() => setFresh(null)} />
          ))}
        </div>
      )}
    </SectionCard>
  );
}
