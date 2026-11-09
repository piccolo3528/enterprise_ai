import { BrainCircuit, X } from "lucide-react";
import { NavLink } from "react-router";

import { NAV_ITEMS } from "./navigation";

function NavItem({ item, onNavigate }) {
  const { to, label, icon: Icon, ready } = item;
  const base = "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium";

  if (!ready) {
    return (
      <span aria-disabled="true" className={`${base} cursor-not-allowed text-slate-500`}>
        <Icon aria-hidden="true" className="size-4" />
        {label}
        <span className="ml-auto rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-slate-400 uppercase">
          Soon
        </span>
      </span>
    );
  }

  return (
    <NavLink
      to={to}
      onClick={onNavigate}
      className={({ isActive }) =>
        `${base} transition-colors ${
          isActive ? "bg-slate-800 text-white" : "text-slate-300 hover:bg-slate-800/60 hover:text-white"
        }`
      }
    >
      <Icon aria-hidden="true" className="size-4" />
      {label}
    </NavLink>
  );
}

/**
 * Always visible on medium screens and up. On phones it slides in over the page when the top
 * bar's menu button is pressed (`open`), with a backdrop that closes it.
 */
export default function Sidebar({ open, onClose }) {
  return (
    <>
      {open && (
        <div
          aria-hidden="true"
          onClick={onClose}
          className="fixed inset-0 z-30 bg-slate-900/50 md:hidden"
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-slate-900 transition-transform md:static md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-16 items-center gap-2.5 px-5">
          <span className="flex size-8 items-center justify-center rounded-lg bg-indigo-500">
            <BrainCircuit aria-hidden="true" className="size-5 text-white" />
          </span>
          <span className="text-sm leading-tight font-semibold text-white">
            Knowledge
            <br />
            Intelligence
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className="ml-auto rounded-md p-1 text-slate-400 hover:text-white md:hidden"
          >
            <X className="size-5" />
          </button>
        </div>
        <nav aria-label="Main" className="flex-1 space-y-1 px-3 py-4">
          {NAV_ITEMS.map((item) => (
            <NavItem key={item.to} item={item} onNavigate={onClose} />
          ))}
        </nav>
        <p className="px-5 py-4 text-xs text-slate-500">Answers come only from your documents.</p>
      </aside>
    </>
  );
}
