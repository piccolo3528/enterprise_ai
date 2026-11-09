import { LogOut, Menu } from "lucide-react";
import { useState } from "react";
import { useLocation } from "react-router";

import { useAuth } from "../../context/AuthContext";
import Button from "../ui/Button";
import { NAV_ITEMS } from "./navigation";

function initials(name) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("");
}

export default function Topbar({ onMenuClick }) {
  const { pathname } = useLocation();
  const { user, signOut } = useAuth();
  const [signingOut, setSigningOut] = useState(false);
  // Only built pages have a route; anything else renders the not-found page.
  const current = NAV_ITEMS.find((item) => item.ready && pathname.startsWith(item.to));

  async function handleSignOut() {
    setSigningOut(true);
    await signOut(); // the route guard then shows the sign-in page
  }

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
      <div className="ml-auto flex items-center gap-3">
        {import.meta.env.DEV && (
          <span className="hidden rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800 sm:inline">
            Development
          </span>
        )}
        {user && (
          <>
            <span className="flex items-center gap-2" title={user.email}>
              <span
                aria-hidden="true"
                className="flex size-8 items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-700"
              >
                {initials(user.full_name)}
              </span>
              <span className="hidden text-sm font-medium text-slate-700 sm:inline">
                {user.full_name}
              </span>
            </span>
            <Button
              variant="ghost"
              size="sm"
              icon={LogOut}
              loading={signingOut}
              onClick={handleSignOut}
            >
              Sign out
            </Button>
          </>
        )}
      </div>
    </header>
  );
}
