import { Outlet, useLocation } from "react-router-dom";
import { useState } from "react";
import { Map, PanelRightClose } from "lucide-react";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import MaritimeMap from "../../pages/MaritimeMap";
export default function AppLayout() {
  const { pathname } = useLocation();
  const [showMap, setShowMap] = useState(false);
  const intelligence = ['/satellite', '/drift', '/attribution'].includes(pathname);
  return <div className="workspace-app">
    <a href="#main-content" className="skip-link">Skip to content</a>
    <Topbar/>
    <div className="workspace-body"><Sidebar/>
      <main id="main-content" className={`workspace-main ${pathname === '/reroute' || pathname === '/map' ? 'map-workspace' : ''}`}>
        {intelligence && <div className="workspace-viewbar"><span>Analysis workspace</span><button onClick={() => setShowMap(v => !v)} aria-pressed={showMap}>{showMap ? <PanelRightClose size={16}/> : <Map size={16}/>} {showMap ? 'Focus on analysis' : 'Show map alongside'}</button></div>}
        <div className={`workspace-content ${intelligence && showMap ? 'with-context-map' : ''}`}>
          {intelligence && showMap && <div className="context-map"><MaritimeMap/></div>}
          <div className="workspace-page">{pathname === '/map' ? <MaritimeMap/> : <Outlet/>}</div>
        </div>
      </main>
    </div>
  </div>;
}
