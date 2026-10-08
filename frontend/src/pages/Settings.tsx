import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, FlaskConical, Settings as SettingsIcon } from "lucide-react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { Shop, ShopUpdate } from "../api/types";
import { useToast } from "../components/toast";
import { Alert, Button, Card, Field, Input, LinkButton, PageHeader, PageLoading, Select, Textarea, Toggle, cx } from "../components/ui";
import { useI18n } from "../i18n";
import { errorMessage, fieldError } from "../lib/errors";

// The language is kept in sync by the panel (Layout), not edited here.
type Form = Omit<Shop, "id" | "tone" | "slug" | "language"> & { tone: "friendly" | "formal" };

function toForm(s: Shop): Form {
  return {
    name: s.name,
    bot_enabled: s.bot_enabled,
    tone: s.tone === "formal" ? "formal" : "friendly",
    use_emoji: s.use_emoji,
    fallback_message: s.fallback_message,
    forbidden_rules: s.forbidden_rules,
    handoff_pause_minutes: s.handoff_pause_minutes,
    currency: s.currency,
  };
}

// Lebanese shops price in dollars or lira; a few others for shops selling abroad. A shop
// already set to another code keeps it in the list.
const CURRENCIES = ["USD", "LBP", "EUR", "AED", "SAR", "QAR", "KWD", "GBP", "CAD", "AUD"];

export default function Settings() {
  const { t } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const shop = useQuery({ queryKey: keys.shop, queryFn: () => api<Shop>("/shop") });
  const [form, setForm] = useState<Form | null>(null);
  const [toneChanged, setToneChanged] = useState(false);

  useEffect(() => {
    if (shop.data && !form) setForm(toForm(shop.data));
  }, [shop.data, form]);

  const original = shop.data ? toForm(shop.data) : null;
  // PATCH only what changed
  const changes: ShopUpdate = {};
  if (form && original) {
    for (const k of Object.keys(form) as (keyof Form)[]) {
      if (form[k] !== original[k]) (changes as Record<string, unknown>)[k] = typeof form[k] === "string" ? (form[k] as string).trim() : form[k];
    }
  }
  const dirty = Object.keys(changes).length > 0;

  const save = useMutation({
    mutationFn: (body: ShopUpdate) => api<Shop>("/shop", { method: "PATCH", json: body }),
    onSuccess: (s, body) => {
      qc.setQueryData(keys.shop, s);
      qc.invalidateQueries({ queryKey: keys.me });
      qc.invalidateQueries({ queryKey: keys.dashboard });
      setForm(toForm(s));
      if (body.tone !== undefined || body.use_emoji !== undefined) setToneChanged(true);
      toast.success(t.common.saved);
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  const header = <PageHeader icon={<SettingsIcon />} title={t.settings.title} />;
  if (shop.isPending || !form)
    return (
      <>
        {header}
        {shop.error ? <Alert kind="error">{errorMessage(shop.error, t)}</Alert> : <PageLoading />}
      </>
    );

  const S = t.panel.settings.sections;
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm({ ...form, [k]: v });
  const err = (name: string) => fieldError(save.error, name, t);
  const pauseInvalid = !Number.isInteger(form.handoff_pause_minutes) || form.handoff_pause_minutes < 0 || form.handoff_pause_minutes > 10080;
  const invalid = !form.name.trim() || !form.fallback_message.trim() || pauseInvalid;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (dirty && !invalid) save.mutate(changes);
  }

  return (
    <form onSubmit={submit} className="max-w-4xl">
      {header}

      {toneChanged && (
        <Alert
          kind="success"
          className="mb-6"
          action={
            <LinkButton to="/playground" size="sm" variant="secondary" icon={<FlaskConical className="size-4" />}>
              {t.nav.playground}
            </LinkButton>
          }
        >
          {t.settings.tryInPlayground}
        </Alert>
      )}

      <Card className="divide-y divide-slate-100">
        <Row title={S.status.title} desc={S.status.desc}>
          <div className="flex items-center justify-between gap-4 rounded-xl bg-slate-50 p-4 ring-1 ring-slate-200/70">
            <div>
              <div className="font-bold text-ink-950">{t.settings.botEnabled}</div>
              <div className="text-sm leading-6 text-slate-500">{t.settings.botEnabledHint}</div>
            </div>
            <Toggle checked={form.bot_enabled} onChange={(v) => set("bot_enabled", v)} label={t.settings.botEnabled} />
          </div>
        </Row>

        <Row title={S.identity.title} desc={S.identity.desc}>
          <Field label={t.settings.name} hint={t.settings.nameHint} error={err("name") ?? (!form.name.trim() ? t.errors.field.name : undefined)}>
            {(id) => <Input id={id} maxLength={120} value={form.name} onChange={(e) => set("name", e.target.value)} />}
          </Field>
          <Field label={t.settings.currency} hint={t.settings.currencyHint} className="mt-4" error={err("currency")}>
            {(id) => (
              <Select id={id} dir="ltr" value={form.currency} onChange={(e) => set("currency", e.target.value)}>
                {(CURRENCIES.includes(form.currency) ? CURRENCIES : [form.currency, ...CURRENCIES]).map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </Row>

        <Row title={S.tone.title} desc={S.tone.desc}>
          <fieldset>
            <legend className="sr-only">{t.settings.tone}</legend>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {(["friendly", "formal"] as const).map((tone) => (
                <ToneOption key={tone} tone={tone} selected={form.tone === tone} emoji={form.use_emoji} onSelect={() => set("tone", tone)} />
              ))}
            </div>
          </fieldset>
          <div className="mt-4 flex items-center justify-between gap-4 rounded-xl bg-slate-50 px-4 py-3 ring-1 ring-slate-200/70">
            <span className="text-sm font-semibold text-ink-900">{t.settings.useEmoji}</span>
            <Toggle checked={form.use_emoji} onChange={(v) => set("use_emoji", v)} label={t.settings.useEmoji} />
          </div>
        </Row>

        <Row title={S.fallback.title} desc={S.fallback.desc}>
          <Field
            label={t.settings.fallback}
            hint={t.settings.fallbackHint}
            error={err("fallback_message") ?? (!form.fallback_message.trim() ? t.errors.field.fallback_message : undefined)}
          >
            {(id) => <Textarea id={id} rows={3} maxLength={1000} value={form.fallback_message} onChange={(e) => set("fallback_message", e.target.value)} />}
          </Field>
        </Row>

        <Row title={S.rules.title} desc={S.rules.desc}>
          <Field label={t.settings.rules} hint={t.settings.rulesHint} error={err("forbidden_rules")}>
            {(id) => (
              <Textarea
                id={id}
                rows={4}
                maxLength={4000}
                placeholder={t.settings.rulesPlaceholder}
                value={form.forbidden_rules}
                onChange={(e) => set("forbidden_rules", e.target.value)}
              />
            )}
          </Field>
        </Row>

        <Row title={S.handoff.title} desc={S.handoff.desc}>
          <Field
            label={t.settings.pauseMinutes}
            hint={t.settings.pauseMinutesHint}
            error={err("handoff_pause_minutes") ?? (pauseInvalid ? t.errors.field.handoff_pause_minutes : undefined)}
          >
            {(id) => (
              <div className="flex items-center gap-3">
                <div className="w-32">
                  <Input
                    id={id}
                    type="number"
                    min={0}
                    max={10080}
                    step={1}
                    dir="ltr"
                    className="num"
                    invalid={pauseInvalid}
                    value={Number.isNaN(form.handoff_pause_minutes) ? "" : form.handoff_pause_minutes}
                    onChange={(e) => set("handoff_pause_minutes", e.target.value === "" ? NaN : Number(e.target.value))}
                  />
                </div>
                <span className="text-sm font-medium text-slate-500">{t.settings.minutes}</span>
              </div>
            )}
          </Field>
        </Row>
      </Card>

      {/* floating save bar while there are changes; clears the phone tab bar */}
      {dirty && (
        <div className="animate-toast-in sticky bottom-[calc(var(--chrome-bottom)+1rem)] z-20 mt-6 flex flex-wrap items-center gap-3 rounded-2xl bg-night-950 px-4 py-3 text-white shadow-float dark:ring-1 dark:ring-white/10 sm:px-5">
          <span className="flex flex-1 items-center gap-2 text-sm font-semibold">
            <span className="size-2 rounded-full bg-amber-400" aria-hidden />
            {t.common.unsavedChanges}
          </span>
          <Button variant="ghostInverse" size="sm" onClick={() => original && setForm(original)}>
            {t.panel.settings.discard}
          </Button>
          <Button type="submit" variant="inverse" size="sm" loading={save.isPending} disabled={invalid}>
            {t.common.save}
          </Button>
        </div>
      )}
    </form>
  );
}

/** A setting group: what it is on the start side, the controls beside it (stacked on phones). */
function Row({ title, desc, children }: { title: string; desc: string; children: ReactNode }) {
  return (
    <section className="grid grid-cols-1 gap-x-10 gap-y-4 p-5 sm:p-6 md:grid-cols-[14rem_minmax(0,1fr)]">
      <div>
        <h2 className="font-bold text-ink-950">{title}</h2>
        <p className="mt-1 text-sm leading-6 text-slate-500">{desc}</p>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

/** A tone choice with a sample reply in that tone (and the current emoji setting). */
function ToneOption({ tone, selected, emoji, onSelect }: { tone: "friendly" | "formal"; selected: boolean; emoji: boolean; onSelect: () => void }) {
  const { t } = useI18n();
  const replies = t.landing.demos.tone.replies;
  const sample = replies[emoji ? (`${tone}Emoji` as const) : tone];
  return (
    <label
      className={cx(
        "relative flex cursor-pointer flex-col gap-3 rounded-2xl p-4 transition-[box-shadow,background-color] duration-200 has-focus-visible:outline-2 has-focus-visible:outline-brand-500",
        selected ? "bg-brand-50/60 ring-2 ring-brand-500" : "bg-surface ring-1 ring-slate-200 hover:ring-brand-300",
      )}
    >
      <input type="radio" name="tone" checked={selected} onChange={onSelect} className="sr-only" />
      <span className="flex items-center justify-between gap-3">
        <span className="font-bold text-ink-950">{tone === "friendly" ? t.settings.toneFriendly : t.settings.toneFormal}</span>
        <span
          aria-hidden
          className={cx("flex size-5 items-center justify-center rounded-full transition-colors", selected ? "bg-brand-600 text-white" : "ring-2 ring-slate-200")}
        >
          {selected && <Check className="size-3" strokeWidth={3.5} />}
        </span>
      </span>
      <span className="text-[11px] font-semibold text-slate-400">{t.panel.settings.sample}</span>
      <span key={sample} className="animate-msg-in -mt-2 w-fit self-end rounded-2xl rounded-se-md bg-brand-600 px-3.5 py-2 text-[13px] leading-6 text-white">
        {sample}
      </span>
    </label>
  );
}
