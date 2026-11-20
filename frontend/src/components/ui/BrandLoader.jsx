import BrandMark from "./BrandMark";

/**
 * The branded loading state: the logo "thinking" plus a short message.
 *
 * - `variant="block"` (default): centred in its area, for a page or section that is loading.
 * - `variant="page"`: larger and centred on the whole screen (the session check).
 * - `variant="inline"`: small, beside its text (e.g. the chat's "Searching your documents…").
 *
 * The message is real text, announced politely by screen readers (role="status"). Buttons and
 * tiny inline rows keep the small Spinner: a logo would be too heavy there.
 */
export default function BrandLoader({ label, variant = "block", className = "" }) {
  if (variant === "inline") {
    return (
      <div role="status" className={`flex items-center gap-3 text-sm text-slate-500 ${className}`}>
        <BrandMark size="sm" animated />
        <span>{label}</span>
      </div>
    );
  }
  const page = variant === "page";
  return (
    <div
      role="status"
      className={`flex flex-col items-center justify-center gap-4 text-sm text-slate-500 ${
        page ? "min-h-[40vh]" : "py-12"
      } ${className}`}
    >
      <BrandMark size={page ? "xl" : "lg"} animated />
      <span>{label}</span>
    </div>
  );
}
