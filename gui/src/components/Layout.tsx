import { Outlet, NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  CheckCircle,
  Eye,
  ShieldAlert,
  Zap,
  Settings,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { RepoSelector } from "@/components/RepoSelector";

const NAV = [
  { to: "/overview", icon: LayoutDashboard, label: "Overview" },
  { to: "/coverage", icon: CheckCircle, label: "Coverage" },
  { to: "/observability", icon: Eye, label: "Observability" },
  { to: "/solid", icon: ShieldAlert, label: "SOLID" },
  { to: "/blast-radius", icon: Zap, label: "Blast Radius" },
];

export function Layout() {
  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 h-full border-r border-border flex flex-col shrink-0">
        {/* Header */}
        <div className="flex items-center gap-2 px-4 h-12 border-b border-border shrink-0">
          <span className="font-bold text-sm tracking-tight">reassure</span>
          <span className="text-[10px] text-muted-foreground font-mono ml-auto">v0.2</span>
        </div>

        {/* Repo selector */}
        <div className="px-3 py-2 border-b border-border">
          <RepoSelector />
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto px-3 py-2 flex flex-col gap-0.5">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 px-3 py-1.5 text-[13px] transition-colors",
                  isActive
                    ? "bg-accent text-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Settings pinned to bottom */}
        <div className="px-3 py-2 border-t border-border">
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 px-3 py-1.5 text-[13px] transition-colors",
                isActive
                  ? "bg-accent text-foreground font-medium"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
              )
            }
          >
            <Settings className="h-4 w-4 shrink-0" />
            <span>Settings</span>
          </NavLink>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 min-w-0 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
