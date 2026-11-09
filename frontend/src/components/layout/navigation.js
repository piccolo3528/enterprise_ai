import { Activity, LayoutDashboard, Library, MessagesSquare, Search, Settings } from "lucide-react";

/**
 * Sidebar entries. Pages that don't exist yet are listed with `ready: false`: they show as
 * greyed-out "Soon" items, not as links to empty placeholder pages.
 */
export const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, ready: false },
  { to: "/knowledge-bases", label: "Knowledge bases", icon: Library, ready: false },
  { to: "/chat", label: "Chat", icon: MessagesSquare, ready: false },
  { to: "/search", label: "Search", icon: Search, ready: false },
  { to: "/status", label: "System status", icon: Activity, ready: true },
  { to: "/settings", label: "Settings", icon: Settings, ready: false },
];
