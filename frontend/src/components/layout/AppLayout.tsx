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
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="w-full max-w-md mx-4 bg-white rounded-2xl shadow-2xl border-2 border-red-500 overflow-hidden animate-in zoom-in-95 slide-in-from-bottom-4 duration-300">
            <div className="bg-red-600 text-white px-5 py-4 flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-white/15 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <div className="text-sm font-black uppercase tracking-wider">Active Maritime Alert</div>
                <div className="text-[11px] text-red-100">{new Date(broadcastAlert.sentAt).toLocaleString()}</div>
              </div>
            </div>
            <div className="px-5 py-4">
              <pre className="whitespace-pre-wrap font-sans text-sm text-ink-800 leading-relaxed">{broadcastAlert.message}</pre>
            </div>
            <div className="px-5 pb-5">
              <button
                onClick={dismissBroadcastAlert}
                className="w-full flex items-center justify-center gap-2 bg-red-600 hover:bg-red-700 text-white font-bold text-sm py-2.5 rounded-lg transition-colors"
              >
                <X className="w-4 h-4" /> Acknowledge
              </button>
            </div>
          </div>
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
