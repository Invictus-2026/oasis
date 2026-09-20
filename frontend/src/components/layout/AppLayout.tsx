import { Outlet, useLocation } from "react-router-dom";
import { AlertTriangle, X } from "lucide-react";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import MaritimeMap from "../../pages/MaritimeMap";
import { useSpillState } from "../../context/SpillContext";

export default function AppLayout() {
  const location = useLocation();
  const isMapOnly = location.pathname === "/map";
  const { broadcastAlert, dismissBroadcastAlert } = useSpillState();

  return (
    <div className="flex flex-col h-screen bg-ink-50 font-sans text-ink-900 overflow-hidden">
      {broadcastAlert && (
        <div className="shrink-0 bg-red-600 text-white px-4 py-2.5 flex items-center gap-3 shadow-md z-50 animate-in slide-in-from-top duration-300">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span className="text-sm font-bold uppercase tracking-wide shrink-0">Active Alert</span>
          <span className="text-sm truncate flex-1">{broadcastAlert.message.split("\n")[0]}</span>
          <span className="text-xs text-red-200 shrink-0 hidden sm:inline">
            {new Date(broadcastAlert.sentAt).toLocaleTimeString()}
          </span>
          <button
            onClick={dismissBroadcastAlert}
            className="shrink-0 rounded-full p-1 hover:bg-red-700 transition-colors"
            aria-label="Dismiss alert"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
      <Topbar />
      <div className="flex flex-1 overflow-hidden relative">
        <Sidebar />
        <main className="app-main min-w-0 flex-1 relative overflow-hidden flex bg-ink-50">
          {/* If it's a full page route that provides its own map (like reroute), just render the Outlet full screen */}
          {location.pathname === "/reroute" ? (
             <Outlet />
          ) : (
            <>
              {/* The map flexes to fill whatever space is left */}
              <div className={`overview-map flex-1 relative min-w-0 z-0 ${!isMapOnly ? "has-panel" : ""}`}>
                 <MaritimeMap />
              </div>
              
              {/* The active intelligence page as a sliding side panel */}
              {!isMapOnly && (
                <div className="intelligence-panel w-[450px] lg:w-[550px] xl:w-[650px] shrink-0 bg-white/95 backdrop-blur-md shadow-[-10px_0_30px_rgba(0,0,0,0.05)] border-l border-ink-200 overflow-y-auto overflow-x-hidden flex flex-col z-20 animate-in slide-in-from-right duration-300 min-w-0 max-w-full">
                   <Outlet />
                </div>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}
