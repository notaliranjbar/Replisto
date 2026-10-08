import { ApiError } from "../api/client";
import type { Dict } from "../i18n/ar";

// Letters only Persian uses (Arabic writes ي and ك): the server still words its errors in Persian.
const PERSIAN = /[پچژکگی]/;

/** Server text still worded in Persian, which the site doesn't show. */
export const isPersian = (text: string | null | undefined): boolean => !!text && PERSIAN.test(text);

/** A message to show for any failed request (docs/FRONTEND.md §2). */
export function errorMessage(err: unknown, t: Dict): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return t.errors.network;
    if (err.detail && !isPersian(err.detail)) return err.detail;
    if (err.status === 502) return t.errors.ai;
    if (err.status === 422 || err.status === 400) return t.errors.invalid;
    if (err.status === 404) return t.errors.notFound;
    if (err.status === 409) return t.errors.conflict;
    if (err.status === 429) return t.errors.tooMany;
    if (err.status === 401 || err.status === 403) return t.errors.forbidden;
  }
  return t.errors.server;
}

/** Field-level message for FastAPI's automatic 422 validation errors. */
export function fieldError(err: unknown, name: string, t: Dict): string | undefined {
  if (!(err instanceof ApiError) || !err.fields[name]) return undefined;
  const messages = t.errors.field as Record<string, string>;
  return messages[name] ?? messages.generic;
}
