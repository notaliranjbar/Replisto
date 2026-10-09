import { LogoMark } from "../components/Logo";
import { LinkButton } from "../components/ui";
import { useI18n } from "../i18n";

export default function NotFound() {
  const { t, f } = useI18n();
  return (
    <div className="animate-pop-in flex flex-col items-center py-20 text-center sm:py-28">
      <LogoMark px={56} className="shadow-lift" />
      <div className="num mt-8 text-7xl font-semibold tracking-tight text-brand-600/15 sm:text-8xl">{f.num(404)}</div>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink-950">{t.notFound.title}</h1>
      <p className="mt-2 max-w-sm text-[15px] leading-7 text-slate-500">{t.panel.notFound.hint}</p>
      <LinkButton to="/" size="lg" className="mt-8">
        {t.notFound.back}
      </LinkButton>
    </div>
  );
}
