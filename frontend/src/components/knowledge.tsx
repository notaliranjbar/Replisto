import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileText, Pencil, Trash } from "lucide-react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { Entry, Section } from "../api/types";
import { useI18n } from "../i18n";
import { errorMessage } from "../lib/errors";
import { useToast } from "./toast";
import { Alert, Button, ConfirmDialog, Field, Input, Textarea } from "./ui";

// Entries of the "multiple" knowledge sections (FAQ, free text, uploaded files).

export function useInvalidateKnowledge() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: keys.knowledge });
    qc.invalidateQueries({ queryKey: keys.dashboard });
  };
}

export function EntryCard({
  section,
  entry,
  startEditing = false,
  onEditEnd,
}: {
  section: Section;
  entry: Entry;
  startEditing?: boolean;
  onEditEnd?: () => void;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const invalidate = useInvalidateKnowledge();
  const [editing, setEditing] = useState(startEditing);
  const [confirm, setConfirm] = useState(false);
  const isFaq = section.key === "faq";

  useEffect(() => {
    if (startEditing) setEditing(true);
  }, [startEditing]);

  const remove = useMutation({
    mutationFn: () => api(`/knowledge/${entry.id}`, { method: "DELETE" }),
    onSuccess: () => {
      setConfirm(false);
      toast.success(t.knowledge.deleted);
      invalidate();
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  if (editing)
    return (
      <EntryEditor
        section={section}
        entry={entry}
        review={startEditing}
        onDone={() => {
          setEditing(false);
          onEditEnd?.();
        }}
      />
    );

  return (
    <div className="group rounded-xl bg-surface p-4 ring-1 ring-slate-200/80 transition-shadow duration-200 hover:shadow-soft hover:ring-brand-200">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          {entry.source_filename && (
            <div className="mb-1.5 inline-flex max-w-full items-center gap-1.5 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
              <FileText className="size-3.5 shrink-0" aria-hidden />
              <span dir="auto" className="truncate">
                {entry.source_filename}
              </span>
            </div>
          )}
          {entry.title && (
            <div className="user-text mb-1 font-semibold text-ink-950">
              {isFaq && <span className="me-1.5 text-brand-700">{t.knowledge.faqQuestion}:</span>}
              {entry.title}
            </div>
          )}
          <div className="user-text line-clamp-6 text-sm leading-7 text-slate-600">{entry.content}</div>
        </div>
        {/* always visible on touch screens; quieter until hover on desktop */}
        <div className="flex shrink-0 gap-0.5 transition-opacity sm:opacity-60 sm:focus-within:opacity-100 sm:group-hover:opacity-100">
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="inline-flex size-9 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-brand-50 hover:text-brand-700"
            aria-label={t.common.edit}
            title={t.common.edit}
          >
            <Pencil className="size-4" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => setConfirm(true)}
            className="inline-flex size-9 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-red-50 hover:text-red-700"
            aria-label={t.common.delete}
            title={t.common.delete}
          >
            <Trash className="size-4" aria-hidden />
          </button>
        </div>
      </div>
      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        onConfirm={() => remove.mutate()}
        loading={remove.isPending}
        danger
        title={t.knowledge.deleteConfirmTitle}
        body={t.knowledge.deleteConfirmBody}
        confirmLabel={t.common.delete}
        cancelLabel={t.common.cancel}
      />
    </div>
  );
}

/** Create (no `entry`) or edit an entry of a multiple section. */
export function EntryEditor({ section, entry, review, onDone }: { section: Section; entry?: Entry; review?: boolean; onDone: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const invalidate = useInvalidateKnowledge();
  const isFaq = section.key === "faq";
  const [title, setTitle] = useState(entry?.title ?? "");
  const [content, setContent] = useState(entry?.content ?? "");

  const save = useMutation({
    mutationFn: () =>
      entry
        ? api<Entry>(`/knowledge/${entry.id}`, { method: "PATCH", json: { title: title.trim(), content } })
        : api<Entry>("/knowledge", { method: "POST", json: { section: section.key, title: title.trim(), content } }),
    onSuccess: () => {
      toast.success(t.common.saved);
      invalidate();
      onDone();
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  const canSave = content.trim().length > 0 && (!isFaq || title.trim().length > 0);

  return (
    <div className="animate-pop-in space-y-4 rounded-xl bg-brand-50/50 p-4 ring-2 ring-brand-200 sm:p-5">
      {review && <Alert kind="info">{t.knowledge.uploadedReview}</Alert>}
      <Field label={isFaq ? t.knowledge.faqQuestion : t.knowledge.itemTitle}>
        {(id) => <Input id={id} maxLength={255} value={title} onChange={(e) => setTitle(e.target.value)} autoFocus={!entry} />}
      </Field>
      <Field label={isFaq ? t.knowledge.faqAnswer : t.knowledge.itemContent}>
        {(id) => (
          <Textarea
            id={id}
            rows={review ? 12 : 4}
            value={content}
            placeholder={entry ? undefined : section.placeholder}
            onChange={(e) => setContent(e.target.value)}
          />
        )}
      </Field>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="secondary" onClick={onDone}>
          {t.common.cancel}
        </Button>
        <Button size="sm" onClick={() => save.mutate()} loading={save.isPending} disabled={!canSave}>
          {t.common.save}
        </Button>
      </div>
    </div>
  );
}
