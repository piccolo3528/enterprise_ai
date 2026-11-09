import { Menu } from "lucide-react";
import { useLocation } from "react-router";

import { NAV_ITEMS } from "./navigation";

export default function Topbar({ onMenuClick }) {
  const { pathname } = useLocation();
  // Only built pages have a route; anything else renders the not-found page.
  const current = NAV_ITEMS.find((item) => item.ready && pathname.startsWith(item.to));

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur sm:px-6 lg:px-8">
      <button
        type="button"
        onClick={onMenuClick}
        aria-label="Open menu"
        className="-ml-1 rounded-md p-1.5 text-slate-500 hover:bg-slate-100 md:hidden"
      >
        <Menu className="size-5" />
      </button>
      <p className="text-sm font-medium text-slate-900">{current?.label ?? "Page not found"}</p>
      {import.meta.env.DEV && (
        <span className="ml-auto rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800">
          Development
        </span>
      )}
    </header>
  );
}
