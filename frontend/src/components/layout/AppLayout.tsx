import { Outlet, useLocation } from "react-router-dom";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import MaritimeMap from "../../pages/MaritimeMap";

export default function AppLayout() {
  const location = useLocation();
  const isMapOnly = location.pathname === "/map" || location.pathname === "/";

  return (
    <div className="flex flex-col h-screen bg-ink-50 font-sans text-ink-900 overflow-hidden">
      <Topbar />
      <div className="flex flex-1 overflow-hidden relative">
        <Sidebar />
        <main className="flex-1 relative overflow-hidden flex bg-ink-50">
          {/* The map flexes to fill whatever space is left */}
          <div className="flex-1 relative min-w-0 z-0">
             <MaritimeMap />
          </div>

          {/* The active intelligence page as a sliding side panel */}
          {!isMapOnly && (
            <div className="w-[450px] lg:w-[550px] xl:w-[650px] shrink-0 bg-white/95 backdrop-blur-md shadow-[-10px_0_30px_rgba(0,0,0,0.05)] border-l border-ink-200 overflow-y-auto flex flex-col z-20 animate-in slide-in-from-right duration-300">
               <Outlet />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
