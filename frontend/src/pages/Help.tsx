import { MessageCircleQuestion } from "lucide-react";
import { AskReplisto } from "../components/AskReplisto";
import { PageHeader } from "../components/ui";
import { useI18n } from "../i18n";

/** "Ask Replisto" as a page: the panel's help chat on phones (desktop also has a floating button). */
export default function Help() {
  const { t } = useI18n();
  return (
    <div className="mx-auto flex h-[calc(100dvh-var(--chrome-top)-var(--chrome-bottom)-3rem)] min-h-[28rem] max-w-2xl flex-col lg:h-[calc(100dvh-5rem)]">
      <PageHeader icon={<MessageCircleQuestion />} title={t.launch.ask.launcher} />
      <div className="min-h-0 flex-1">
        <AskReplisto compact />
      </div>
    </div>
  );
}
