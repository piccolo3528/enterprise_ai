import { LoaderCircle } from "lucide-react";

export default function Spinner({ label = "Loading", className = "size-5" }) {
  return (
    <span role="status" className="inline-flex items-center">
      <LoaderCircle aria-hidden="true" className={`animate-spin text-slate-400 ${className}`} />
      {/* Announced by screen readers; invisible on screen. */}
      <span className="sr-only">{label}</span>
    </span>
  );
}
