import { useCallback, useEffect, useRef, useState } from "react";
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
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import UploadPanel from "./UploadPanel";

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

const MIN_WIDTH = 256;
const MAX_WIDTH = 480;
const DEFAULT_WIDTH = 288;
const WIDTH_KEY = "oasis_sidebar_width";
const COLLAPSED_WIDTH = 72;
const COLLAPSED_KEY = "oasis_sidebar_collapsed";

export default function Sidebar() {
  const [width, setWidth] = useState(() => {
    const saved = Number(localStorage.getItem(WIDTH_KEY));
    return saved >= MIN_WIDTH && saved <= MAX_WIDTH ? saved : DEFAULT_WIDTH;
  });
  const [resizing, setResizing] = useState(false);
  const [compact, setCompact] = useState(() => window.matchMedia("(max-width: 1200px)").matches);
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSED_KEY) === "1");
  const startX = useRef(0);
  const startWidth = useRef(width);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1200px)");
    const onChange = (e: MediaQueryListEvent) => setCompact(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const onMouseMove = useCallback((e: MouseEvent) => {
    const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth.current + (e.clientX - startX.current)));
    setWidth(next);
  }, []);

  const onMouseUp = useCallback(() => {
    setResizing(false);
    document.removeEventListener("mousemove", onMouseMove);
    document.removeEventListener("mouseup", onMouseUp);
  }, [onMouseMove]);

  useEffect(() => {
    localStorage.setItem(WIDTH_KEY, String(width));
  }, [width]);

  useEffect(() => {
    localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  const toggleCollapsed = () => setCollapsed((c) => !c);

  const onMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    startX.current = e.clientX;
    startWidth.current = width;
    setResizing(true);
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  };

  return (
    <aside
      style={compact ? undefined : { width: collapsed ? COLLAPSED_WIDTH : width }}
      className={`app-sidebar relative bg-white border-r border-ink-200 flex flex-col h-full shrink-0 ${resizing ? "" : "transition-[width] duration-150"}`}
    >
      <div className="flex-1 overflow-y-auto overflow-x-hidden py-4">
        <div className={`flex px-3 mb-2 ${collapsed ? "justify-center" : "justify-end"}`}>
          <button
            onClick={toggleCollapsed}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="p-1.5 rounded-md text-ink-400 hover:text-ink-900 hover:bg-ink-100 transition-colors shrink-0"
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </button>
        </div>

        <nav className="space-y-1 px-3">
          {navItems.map((item) => (
            <NavLink
              key={item.name}
              to={item.path}
              title={item.name}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${
                  collapsed ? "justify-center" : ""
                } ${
                  isActive
                    ? "bg-blue-50 text-blue-700"
                    : "text-ink-600 hover:bg-ink-50 hover:text-ink-900"
                }`
              }
            >
              <item.icon className="h-5 w-5 shrink-0" />
              {!collapsed && <span>{item.name}</span>}
            </NavLink>
          ))}
        </nav>

        {!compact && !collapsed && (
          <div className="mt-6 pt-5 mx-3 border-t border-ink-200">
            <UploadPanel />
          </div>
        )}
      </div>

      {!compact && !collapsed && (
        <div
          onMouseDown={onMouseDown}
          className={`absolute top-0 right-0 h-full w-1.5 cursor-col-resize group ${resizing ? "bg-blue-400/40" : ""}`}
        >
          <div className="h-full w-px bg-transparent group-hover:bg-blue-400/60 mx-auto" />
        </div>
      )}
    </aside>
  );
}
