import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Map as MapIcon,
  Satellite,
  Ship,
  Wind,
  Target,
  FileText,
  Bell,
  Database,
} from "lucide-react";

const navItems = [
  { name: "Overview", path: "/", icon: LayoutDashboard },
  { name: "Maritime Map", path: "/map", icon: MapIcon },
  { name: "Satellite Intelligence", path: "/satellite", icon: Satellite },
  // { name: "Vessel Intelligence", path: "/vessel", icon: Ship },
  { name: "Drift Intelligence", path: "/drift", icon: Wind },
  { name: "Attribution", path: "/attribution", icon: Target },
  { name: "Reroute Simulation", path: "/reroute", icon: Ship },
  { name: "Reports", path: "/reports", icon: FileText },
  { name: "Alerts", path: "/alerts", icon: Bell },
  { name: "Data Sources", path: "/data", icon: Database },
  // { name: "Models", path: "/models", icon: Cpu },
  // { name: "Settings", path: "/settings", icon: Settings },
];

export default function Sidebar() {
  return (
    <aside className="w-64 bg-white border-r border-ink-200 flex flex-col h-full shrink-0">
      <div className="flex-1 overflow-y-auto py-4">
        <nav className="space-y-1 px-3">
          {navItems.map((item) => (
            <NavLink
              key={item.name}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-blue-50 text-blue-700"
                    : "text-ink-600 hover:bg-ink-50 hover:text-ink-900"
                }`
              }
            >
              <item.icon className="h-5 w-5 shrink-0" />
              {item.name}
            </NavLink>
          ))}
        </nav>
      </div>
    </aside>
  );
}
