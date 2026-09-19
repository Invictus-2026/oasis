import { Moon, Sun, Waves, ArrowUpRight } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { useTheme } from "../../context/ThemeContext";

const names: Record<string, string> = { '/': 'Overview', '/map': 'Maritime map', '/satellite': 'Satellite intelligence', '/drift': 'Drift intelligence', '/attribution': 'Attribution', '/reroute': 'Route planner', '/reports': 'Reports', '/alerts': 'Alerts', '/data': 'Data sources' };
export default function Topbar() {
  const { theme, toggleTheme } = useTheme();
  const { pathname } = useLocation();
  return <header className="workspace-topbar">
    <Link to="/" className="brand-lockup" aria-label="SpillTrace overview"><span className="brand-symbol"><Waves size={23} /></span><span>SpillTrace<span className="brand-subtitle">OCEAN INTELLIGENCE</span></span></Link>
    <div className="workspace-breadcrumb"><span>Workspace</span><span>/</span><strong>{names[pathname] ?? 'Intelligence'}</strong></div>
    <div className="topbar-actions">
      <Link to="/map" className="map-shortcut">Explore map <ArrowUpRight size={15} /></Link>
      <button className="theme-switch" onClick={toggleTheme} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`} title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
        {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}<span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
      </button>
    </div>
  </header>;
}
