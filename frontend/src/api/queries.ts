import { useQuery } from "@tanstack/react-query";
import { api } from "./client";
import type { Dashboard, Sections, User } from "./types";

export const keys = {
  me: ["me"] as const,
  dashboard: ["dashboard"] as const,
  shop: ["shop"] as const,
  instagram: ["instagram"] as const,
  posts: ["instagram", "posts"] as const,
  sections: ["knowledge", "sections"] as const,
  knowledge: ["knowledge", "entries"] as const,
  source: ["products", "source"] as const,
  fields: ["products", "fields"] as const,
  products: (q: string, offset: number, origin = "", stock = "") => ["products", "list", q, offset, origin, stock] as const,
  productSummary: ["products", "summary"] as const,
  billing: ["billing"] as const,
  walletEntries: ["billing", "entries"] as const,
  proposals: ["teach", "proposals"] as const,
  conversations: ["conversations"] as const,
  conversation: (id: string) => ["conversation", id] as const,
  handoffs: ["handoffs"] as const,
  unanswered: ["unanswered"] as const,
  comments: (view: string, category: string) => ["comments", view, category] as const,
  stories: ["stories"] as const,
  insights: ["insights"] as const,
};

export function useMe() {
  return useQuery({ queryKey: keys.me, queryFn: () => api<User>("/me"), staleTime: 60_000 });
}

/** Polled everywhere in the panel: it drives the menu badges, tab title and notifications. */
export function useDashboard() {
  return useQuery({
    queryKey: keys.dashboard,
    queryFn: () => api<Dashboard>("/dashboard"),
    refetchInterval: 20_000,
    // keep polling in a background tab so the owner gets notified of new handoffs
    refetchIntervalInBackground: true,
  });
}

export function useSections() {
  return useQuery({ queryKey: keys.sections, queryFn: () => api<Sections>("/knowledge/sections"), staleTime: Infinity });
}
