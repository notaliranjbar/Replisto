import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { Dashboard, HandoffPage } from "../api/types";
import { useI18n } from "../i18n";
import { customerName } from "./format";

function notificationsSupported(): boolean {
  return typeof window !== "undefined" && "Notification" in window;
}

export function useNotificationPermission() {
  const [perm, setPerm] = useState<NotificationPermission | "unsupported">(() =>
    notificationsSupported() ? Notification.permission : "unsupported",
  );
  const request = async () => {
    if (!notificationsSupported()) return;
    setPerm(await Notification.requestPermission());
  };
  return { permission: perm, request };
}

/**
 * Watches the polled dashboard: when open handoffs go up, refreshes the lists and
 * shows a browser notification for the newest one (if the user allowed it).
 */
export function useHandoffWatcher(dashboard: Dashboard | undefined) {
  const qc = useQueryClient();
  const { t, f } = useI18n();
  const prev = useRef<number | null>(null);

  useEffect(() => {
    if (!dashboard) return;
    const count = dashboard.open_handoffs;
    const before = prev.current;
    prev.current = count;
    if (before === null || count <= before) return;

    qc.invalidateQueries({ queryKey: keys.handoffs });
    qc.invalidateQueries({ queryKey: keys.conversations });
    qc.invalidateQueries({ queryKey: keys.unanswered });

    if (!notificationsSupported() || Notification.permission !== "granted") return;
    api<HandoffPage>("/handoffs", { query: { status: "open", limit: 100 } })
      .then((page) => {
        const newest = [...page.items].sort((a, b) => b.handoff.handed_off_at.localeCompare(a.handoff.handed_off_at))[0];
        if (!newest) return;
        const name = customerName(newest.customer_username, newest.customer_igsid, t, f, newest.customer_name);
        const n = new Notification(t.handoffs.notificationTitle(name), {
          body: newest.handoff.question.replace(/\s+/g, " ").slice(0, 140),
          tag: `handoff-${newest.conversation_id}`,
          icon: "/brand/replisto-logo-192.png",
        });
        n.onclick = () => {
          window.focus();
          window.location.assign("/handoffs");
        };
      })
      .catch(() => {
        // a missed notification isn't worth an error message
      });
  }, [dashboard, qc, t, f]);
}
