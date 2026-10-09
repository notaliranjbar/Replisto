import { useState } from "react";
import { Check, Copy, Globe } from "lucide-react";
import type { Channel } from "../api/types";
import { useI18n } from "../i18n";
import { ChannelMark } from "./site/channels";
import { Button, cx } from "./ui";

/** The channel's logo in its own colour, for conversation lists and headers. */
export function ChannelIcon({ channel, className }: { channel: Channel; className?: string }) {
  if (channel === "web") return <Globe aria-hidden className={cx("size-3.5 shrink-0 text-brand-600", className)} />;
  return <ChannelMark channel={channel} className={cx("size-3.5", "text-pink-600", className)} />;
}

/** The channel's name for a conversation ("Instagram", "Website"). */
export function useChannelLabel() {
  const { t } = useI18n();
  return (channel: Channel) => (channel === "web" ? t.launch.channel.web : t.launch.channel.instagram);
}

export function CopyButton({ value, size = "sm" }: { value: string; size?: "sm" | "md" }) {
  const { t } = useI18n();
  const [done, setDone] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      // older browsers: select the text so the owner can copy it by hand
      window.prompt("", value);
    }
    setDone(true);
    setTimeout(() => setDone(false), 1800);
  }
  return (
    <Button size={size} variant="secondary" icon={done ? <Check className="size-4 text-emerald-600" /> : <Copy className="size-4" />} onClick={copy}>
      {done ? t.launch.clipboard.copied : t.launch.clipboard.copy}
    </Button>
  );
}
