import { useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent } from "react";
import { useLocation } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Clock, Film, ImagePlus, Pencil, Send, Trash2, Upload } from "lucide-react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { Story, StoryList } from "../api/types";
import { InstagramNotice } from "../components/social";
import { useToast } from "../components/toast";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, Field, Input, PageHeader, PageLoading, Textarea, cx } from "../components/ui";
import { useI18n } from "../i18n";
import { errorMessage } from "../lib/errors";

const ACCEPT = "image/jpeg,image/png,image/webp,video/mp4,video/quicktime";

/** "2026-10-09T18:00" for a datetime-local input, in the browser's time zone. */
function toLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** The next full hour, at least 30 minutes from now. */
function defaultTime(): string {
  const d = new Date(Date.now() + 30 * 60_000);
  d.setMinutes(0, 0, 0);
  d.setHours(d.getHours() + 1);
  return toLocalInput(d);
}

export default function Stories() {
  const { t } = useI18n();
  const S = t.social.stories;
  const list = useQuery({ queryKey: keys.stories, queryFn: () => api<StoryList>("/stories"), refetchInterval: 30_000 });

  return (
    <div className="max-w-6xl">
      <PageHeader icon={<CalendarClock />} title={S.title} subtitle={S.subtitle} />
      {list.data && <InstagramNotice connected={list.data.available || list.data.needs_reconnect} needsReconnect={list.data.needs_reconnect} />}
      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <NewStory />
        <div className="min-w-0 space-y-6">
          {list.isPending ? (
            <PageLoading />
          ) : list.error ? (
            <Alert kind="error">{errorMessage(list.error, t)}</Alert>
          ) : (
            <>
              <Upcoming stories={list.data.upcoming} />
              <Past stories={list.data.past} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function useRefreshStories() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: keys.stories });
    qc.invalidateQueries({ queryKey: keys.dashboard });
  };
}

function NewStory() {
  const { t } = useI18n();
  const S = t.social.stories;
  const toast = useToast();
  const refresh = useRefreshStories();
  const location = useLocation();
  const fromIdea = (location.state as { note?: string } | null)?.note ?? "";
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [when, setWhen] = useState(defaultTime);
  const [note, setNote] = useState(fromIdea);
  const [dragging, setDragging] = useState(false);
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview]);

  const create = useMutation({
    mutationFn: async (now: boolean) => {
      const form = new FormData();
      form.append("file", file!);
      form.append("scheduled_at", (now ? new Date() : new Date(when)).toISOString());
      form.append("note", note.trim());
      const story = await api<Story>("/stories", { method: "POST", form });
      return now ? api<Story>(`/stories/${story.id}/publish-now`, { method: "POST" }) : story;
    },
    onSuccess: (story, now) => {
      if (story.status === "failed") toast.error(story.error ?? S.status.failed);
      else toast.success(now ? S.published : S.scheduled);
      setFile(null);
      setNote("");
      setWhen(defaultTime());
      refresh();
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  const pick = (f: File | undefined) => f && setFile(f);
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    pick(e.dataTransfer.files[0]);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (file) create.mutate(false);
  };

  return (
    <Card className="lg:sticky lg:top-6">
      <CardHeader icon={<ImagePlus />} title={S.newTitle} subtitle={fromIdea ? S.fromIdea : undefined} />
      <form onSubmit={submit} className="space-y-4 p-4 sm:p-5">
        <input ref={input} type="file" accept={ACCEPT} className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
        {preview && file ? (
          <div className="flex items-end gap-3">
            <div className="aspect-[9/16] w-28 overflow-hidden rounded-lg border border-slate-200 bg-slate-900">
              {file.type.startsWith("video/") ? (
                <video src={preview} muted playsInline className="size-full object-cover" />
              ) : (
                <img src={preview} alt="" className="size-full object-cover" />
              )}
            </div>
            <div className="min-w-0 flex-1 space-y-2">
              <p className="truncate text-xs text-slate-500" dir="auto">
                {file.name}
              </p>
              <Button size="sm" variant="secondary" onClick={() => input.current?.click()}>
                {S.change}
              </Button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => input.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={cx(
              "flex w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-4 py-8 text-center transition-colors",
              dragging ? "border-brand-500 bg-brand-50" : "border-slate-300 hover:border-brand-400 hover:bg-slate-50",
            )}
          >
            <Upload className="size-6 text-slate-400" aria-hidden />
            <span className="text-sm font-medium text-ink-900">{S.choose}</span>
            <span className="text-xs leading-5 text-slate-500">{S.chooseHint}</span>
          </button>
        )}

        <Field label={S.when}>{(id) => <Input id={id} type="datetime-local" value={when} min={toLocalInput(new Date())} onChange={(e) => setWhen(e.target.value)} />}</Field>
        <Field label={S.note} hint={S.noteHint}>
          {(id) => <Textarea id={id} rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} placeholder={S.notePlaceholder} />}
        </Field>
        <div className="flex gap-2">
          <Button type="submit" className="flex-1" icon={<CalendarClock className="size-4" />} loading={create.isPending && create.variables === false} disabled={!file || !when || create.isPending}>
            {S.schedule}
          </Button>
          <Button variant="secondary" icon={<Send className="size-4 rtl:-scale-x-100" />} loading={create.isPending && create.variables === true} disabled={!file || create.isPending} onClick={() => create.mutate(true)}>
            {S.publishNow}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function dayKey(iso: string) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function Upcoming({ stories }: { stories: Story[] }) {
  const { t, f } = useI18n();
  const S = t.social.stories;
  const today = dayKey(new Date().toISOString());
  const tomorrow = dayKey(new Date(Date.now() + 86_400_000).toISOString());
  const groups = new Map<string, Story[]>();
  for (const story of stories) {
    const key = dayKey(story.scheduled_at);
    groups.set(key, [...(groups.get(key) ?? []), story]);
  }
  return (
    <Card>
      <CardHeader icon={<Clock />} title={S.upcoming} />
      {stories.length === 0 ? (
        <EmptyState icon={<CalendarClock />} title={S.emptyUpcoming} />
      ) : (
        <div className="divide-y divide-slate-100">
          {[...groups.entries()].map(([key, items]) => (
            <section key={key} className="p-4 sm:p-5">
              <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-500">
                {key === today ? S.today : key === tomorrow ? S.tomorrow : f.date(items[0].scheduled_at)}
              </h3>
              <ol className="space-y-4">
                {items.map((story) => (
                  <StoryRow key={story.id} story={story} />
                ))}
              </ol>
            </section>
          ))}
        </div>
      )}
    </Card>
  );
}

function Past({ stories }: { stories: Story[] }) {
  const { t } = useI18n();
  const S = t.social.stories;
  return (
    <Card>
      <CardHeader icon={<Film />} title={S.past} />
      {stories.length === 0 ? (
        <EmptyState icon={<Film />} title={S.emptyPast} />
      ) : (
        <ol className="space-y-4 p-4 sm:p-5">
          {stories.map((story) => (
            <StoryRow key={story.id} story={story} />
          ))}
        </ol>
      )}
    </Card>
  );
}

function StoryRow({ story }: { story: Story }) {
  const { t, f } = useI18n();
  const S = t.social.stories;
  const toast = useToast();
  const refresh = useRefreshStories();
  const [editing, setEditing] = useState<"note" | "time" | null>(null);
  const [note, setNote] = useState(story.note);
  const [when, setWhen] = useState(toLocalInput(new Date(story.scheduled_at)));
  const waiting = story.status === "scheduled";

  const patch = useMutation({
    mutationFn: (json: { note?: string; scheduled_at?: string }) => api<Story>(`/stories/${story.id}`, { method: "PATCH", json }),
    onSuccess: (_, json) => {
      toast.success(json.note !== undefined ? S.noteSaved : S.timeSaved);
      setEditing(null);
      refresh();
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });
  const remove = useMutation({
    mutationFn: () => api(`/stories/${story.id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success(S.cancelled);
      refresh();
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });
  const publish = useMutation({
    mutationFn: () => api<Story>(`/stories/${story.id}/publish-now`, { method: "POST" }),
    onSuccess: (s) => {
      if (s.status === "failed") toast.error(s.error ?? S.status.failed);
      else toast.success(S.published);
      refresh();
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  const tone = story.status === "published" ? "green" : story.status === "failed" ? "red" : story.status === "processing" ? "amber" : "brand";
  return (
    <li className="flex gap-4">
      <a href={story.media_url} target="_blank" rel="noopener noreferrer" className="block aspect-[9/16] w-20 shrink-0 overflow-hidden rounded-lg border border-slate-200 bg-slate-900 sm:w-24">
        {story.media_kind === "video" ? (
          <video src={story.media_url} muted playsInline preload="metadata" className="size-full object-cover" />
        ) : (
          <img src={story.media_url} alt="" loading="lazy" className="size-full object-cover" />
        )}
      </a>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={tone}>{S.status[story.status]}</Badge>
          <span className="num text-sm font-medium text-ink-900">
            {story.status === "published" && story.published_at ? S.publishedAt(f.dateTime(story.published_at)) : waiting ? S.at(f.time(story.scheduled_at)) : f.dateTime(story.scheduled_at)}
          </span>
          {story.media_kind === "video" && <span className="text-xs text-slate-400">{S.video}</span>}
        </div>

        {editing === "note" ? (
          <form
            className="mt-2 space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              patch.mutate({ note: note.trim() });
            }}
          >
            <Textarea autoFocus rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} placeholder={S.notePlaceholder} />
            <div className="flex gap-2">
              <Button type="submit" size="sm" loading={patch.isPending}>
                {t.common.save}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
                {t.common.cancel}
              </Button>
            </div>
          </form>
        ) : (
          <p dir="auto" className={cx("mt-2 text-sm leading-6", story.note ? "text-ink-800" : "text-slate-400")}>
            {story.note || S.notePlaceholder}
          </p>
        )}

        {editing === "time" && (
          <form
            className="mt-2 flex flex-wrap gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              patch.mutate({ scheduled_at: new Date(when).toISOString() });
            }}
          >
            <Input type="datetime-local" value={when} min={toLocalInput(new Date())} onChange={(e) => setWhen(e.target.value)} className="w-auto" />
            <Button type="submit" size="sm" loading={patch.isPending}>
              {t.common.save}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
              {t.common.cancel}
            </Button>
          </form>
        )}

        {story.error && <p className="mt-2 text-xs leading-5 text-red-700">{story.error}</p>}

        {!editing && (
          <div className="mt-2 flex flex-wrap gap-1">
            {waiting && (
              <Button size="sm" variant="ghost" icon={<Send className="size-4 rtl:-scale-x-100" />} loading={publish.isPending} onClick={() => publish.mutate()}>
                {S.publishNow}
              </Button>
            )}
            {waiting && (
              <Button size="sm" variant="ghost" icon={<Clock className="size-4" />} onClick={() => setEditing("time")}>
                {S.reschedule}
              </Button>
            )}
            <Button size="sm" variant="ghost" icon={<Pencil className="size-4" />} onClick={() => setEditing("note")}>
              {S.editNote}
            </Button>
            {story.status !== "processing" && (
              <Button size="sm" variant="ghost" icon={<Trash2 className="size-4" />} loading={remove.isPending} onClick={() => remove.mutate()}>
                <span className="text-red-700">{waiting ? S.cancel : S.remove}</span>
              </Button>
            )}
          </div>
        )}
      </div>
    </li>
  );
}
