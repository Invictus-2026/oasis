import { NavLink } from "react-router-dom";
import { LayoutDashboard, Map, Satellite, Wind, Target, Ship, FileText, Bell, Database, ArrowUpRight, Compass } from "lucide-react";
const groups = [
  { label: 'WORKSPACE', items: [
    { name: 'Overview', path: '/', icon: LayoutDashboard },
    { name: 'Maritime map', path: '/map', icon: Map },
  ]},
  { label: 'INTELLIGENCE', items: [
    { name: 'Satellite', path: '/satellite', icon: Satellite },
    { name: 'Drift analysis', path: '/drift', icon: Wind },
    { name: 'Attribution', path: '/attribution', icon: Target },
    { name: 'Route planner', path: '/reroute', icon: Ship },
  ]},
  { label: 'RESOURCES', items: [
    { name: 'Reports', path: '/reports', icon: FileText },
    { name: 'Alerts', path: '/alerts', icon: Bell },
    { name: 'Data sources', path: '/data', icon: Database },
  ]},
];
export default function Sidebar() {
  return <aside className="workspace-sidebar">
    <div className="workspace-label"><span className="workspace-avatar"><Compass size={20}/></span><div><strong>Maritime operations</strong><small>Analysis workspace</small></div></div>
    <nav aria-label="Main navigation">{groups.map(group => <div className="nav-group" key={group.label}><p>{group.label}</p>{group.items.map(item => <NavLink key={item.path} to={item.path} end={item.path === '/'} title={item.name} aria-label={item.name} className={({isActive}) => `workspace-nav-link ${isActive ? 'is-active' : ''}`}><item.icon size={19}/><span>{item.name}</span></NavLink>)}</div>)}</nav>
    <div className="sidebar-note"><span className="eyebrow">FROM DETECTION TO DECISION</span><p>A clearer view of<br/>what’s on the water.</p><NavLink to="/reroute">Plan a voyage <ArrowUpRight size={16}/></NavLink></div>
    <div className="sidebar-footer"><span className="status-dot"/> SpillTrace <span>v0.1</span></div>
  </aside>;
}
