import { Link } from "react-router-dom";
import { Activity, ArrowRight, ArrowUpRight, Waves, Satellite, Navigation, Wind, Target, Ship, ScanLine } from "lucide-react";
import { useSpillState } from "../context/SpillContext";
import { km2, pct } from "../lib/format";

export default function Overview() {
  const { caseMeta, detection, forecast, attribution, hindcast, runHindcast, runAttribute, drifting, attributing } = useSpillState();
  const slicks = detection?.slicks ?? [];
  const area = slicks.reduce((total, slick) => total + slick.geometry.area_km2, 0);
  const correlate = async () => { const history = hindcast ?? await runHindcast(); if (history) await runAttribute(undefined, history); };
  const metrics = [
    { label: 'Detected spills', value: detection ? String(slicks.length).padStart(2, '0') : '—', detail: detection ? 'In the current scene' : 'Awaiting detection', icon: Activity, tone: 'mint' },
    { label: 'Surface coverage', value: detection ? km2(area) : '—', detail: 'Combined detected slick area', icon: Waves, tone: 'amber' },
    { label: 'Candidate vessels', value: attribution ? String(attribution.after_filter).padStart(2, '0') : '—', detail: attribution ? 'After correlation filters' : 'Correlation not run', icon: Ship, tone: 'violet' },
    { label: 'Coastal impact', value: forecast ? (forecast.impact_flags.length ? 'Flagged' : 'None predicted') : 'Pending', detail: forecast ? 'Based on current forecast' : 'Run a drift forecast', icon: Wind, tone: 'mint' },
  ];
  return <div className="dashboard page-shell">
    <div className="dashboard-heading"><div><span className="eyebrow">YOUR OCEAN, IN FOCUS</span><h1>Maritime overview<span>.</span></h1><p>Understand the spill. Trace its origin. Plan what comes next.</p></div><Link to="/satellite" className="action-primary"><ScanLine size={17}/> Open satellite analysis <ArrowUpRight size={16}/></Link></div>
    <section className="overview-hero">
      <div className="hero-copy"><span className="hero-kicker"><span/> MARITIME INTELLIGENCE</span><h2>See the bigger picture.<br/>Act with clarity.</h2><p>Connect satellite observations, ocean drift and vessel activity in one analysis workspace.</p><Link to="/map">Explore the maritime map <ArrowRight size={18}/></Link></div>
      <div className="ocean-graphic" aria-hidden="true"><div className="radar-ring ring-one"/><div className="radar-ring ring-two"/><div className="radar-ring ring-three"/><div className="radar-axis"/><div className="radar-dot dot-one"/><div className="radar-dot dot-two"/><div className="radar-vessel"><Navigation size={30}/></div><span className="radar-caption">OBSERVE / UNDERSTAND / RESPOND</span></div>
    </section>
    <div className="overview-metrics">{metrics.map(metric => <section className="metric-card" key={metric.label}><div className="metric-top"><span>{metric.label}</span><span className={`metric-icon ${metric.tone}`}><metric.icon size={18}/></span></div><strong>{metric.value}</strong><p>{metric.detail}</p></section>)}</div>
    <div className="dashboard-columns">
      <section className="dashboard-card"><header><div><span className="eyebrow">CURRENT OBSERVATION</span><h2>Scene intelligence</h2></div><Satellite size={20}/></header><div className="scene-summary"><span className="scene-icon"><Waves size={28}/></span><div><h3>{caseMeta?.name ?? 'Loading observation…'}</h3><p>{caseMeta ? new Date(caseMeta.acquired_at).toLocaleString() : 'Waiting for scene metadata'}</p></div></div><dl className="scene-facts"><div><dt>Scene identifier</dt><dd>{caseMeta?.scene_id ?? '—'}</dd></div><div><dt>Detection confidence</dt><dd>{slicks[0] ? `${pct(slicks[0].confidence)} · first slick` : 'Not assessed'}</dd></div><div><dt>Drift analysis</dt><dd>{hindcast ? 'Hindcast available' : 'Not run'}</dd></div><div><dt>Forecast</dt><dd>{forecast ? 'Forecast available' : 'Not run'}</dd></div></dl><Link to="/satellite" className="card-text-link">Inspect satellite evidence <ArrowRight size={16}/></Link></section>
      <section className="dashboard-card"><header><div><span className="eyebrow">INVESTIGATION WORKFLOW</span><h2>Your next steps</h2></div><Target size={20}/></header><div className="workflow-list">{[
        { n:'01', title:'Detect & inspect', text:'Review satellite imagery and spill boundaries.', url:'/satellite', icon:Satellite },
        { n:'02', title:'Understand the drift', text:'Explore the likely origin and future spread.', url:'/drift', icon:Wind },
        { n:'03', title:'Plan the voyage', text:'Compare hazard arrival and clearance times.', url:'/reroute', icon:Navigation },
      ].map(step => <Link to={step.url} key={step.n}><span className="step-number">{step.n}</span><div><h3>{step.title}</h3><p>{step.text}</p></div><ArrowUpRight size={18}/></Link>)}</div></section>
    </div>
    <section className="dashboard-card"><header><div><span className="eyebrow">VESSEL ATTRIBUTION</span><h2>Follow the evidence</h2></div><Link to="/attribution" className="card-text-link">View analysis <ArrowUpRight size={16}/></Link></header>{attribution ? <div className="candidate-grid">{attribution.candidates.length ? attribution.candidates.slice(0,4).map((c,i) => <Link to="/attribution" className="candidate-card" key={c.mmsi}><span className="step-number">{String(i+1).padStart(2,'0')}</span><div><h3>{c.name}</h3><p>MMSI {c.mmsi}</p></div><strong>{c.score.toFixed(3)}<small>Match score</small></strong></Link>) : <p className="dashboard-empty">No candidate vessels remained after filtering.</p>}</div> : <div className="dashboard-empty"><span className="empty-icon"><Ship size={25}/></span><div><h3>Ready to connect the dots?</h3><p>Run AIS correlation to identify vessels associated with the detected spill.</p></div><button onClick={correlate} disabled={!!drifting || attributing} className="action-secondary">{drifting || attributing ? 'Correlating…' : 'Run AIS correlation'}<ArrowRight size={16}/></button></div>}</section>
    <footer className="dashboard-footer"><Waves size={16}/> SpillTrace · Maritime intelligence workspace <span>Observations inform decisions.</span></footer>
  </div>;
}
