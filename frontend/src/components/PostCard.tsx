import { ExternalLink, Images } from "lucide-react";
import { useI18n } from "../i18n";
import { cx } from "./ui";

/** How the backend records a shared post in a conversation: "[post] <permalink>". */
export const POST_MARKER = "[post]";

export function sharedPostUrl(text: string): string | null {
  if (!text.startsWith(POST_MARKER)) return null;
  const ref = text.slice(POST_MARKER.length).trim();
  // "img:<url>" is a product photo
  if (ref.startsWith("img:")) return ref.slice(4);
  return ref;
}

type Post = { permalink: string; caption?: string | null; preview_url?: string | null };

/** A product post the bot sent (an Instagram post card or a photo). */
export function PostCard({ post, className, fluid }: { post: Post; className?: string; fluid?: boolean }) {
  const { t } = useI18n();
  const image = /\.(jpe?g|png|webp|gif)(\?|$)/i.test(post.permalink);
  return (
    <a
      href={post.permalink || undefined}
      target="_blank"
      rel="noopener noreferrer"
      className={cx(
        "flex max-w-full items-center gap-3 rounded-xl border border-slate-200 bg-surface p-2 text-start shadow-sm transition-[border-color,box-shadow,transform] duration-200 hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-md",
        fluid ? "w-full" : "w-64",
        className,
      )}
    >
      {post.preview_url || image ? (
        <img src={post.preview_url || post.permalink} alt="" className="size-14 shrink-0 rounded-lg object-cover" loading="lazy" />
      ) : (
        <span className="flex size-14 shrink-0 items-center justify-center rounded-lg bg-brand-100 text-brand-700">
          <Images className="size-6" />
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block text-xs font-semibold text-slate-800">{t.posts.cardTitle}</span>
        {post.caption && <span className="user-text line-clamp-2 text-xs text-slate-500">{post.caption}</span>}
        <span className="mt-0.5 inline-flex items-center gap-1 text-[11px] font-medium text-brand-700">
          {t.posts.view}
          <ExternalLink className="size-3" />
        </span>
      </span>
    </a>
  );
}
