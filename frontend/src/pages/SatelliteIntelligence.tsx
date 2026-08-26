import { useSpillState } from "../context/SpillContext";
import DetectionPanel from "../components/DetectionPanel";
import ErrorBoundary from "../components/ErrorBoundary";

export default function SatelliteIntelligence() {
  const { detection, detecting, method, runDetect, onFocusLookalike } = useSpillState();

  return (
    <div className="page-shell">
      <header className="page-header">
        <h2>Satellite Intelligence</h2>
        <p>Analyze Synthetic Aperture Radar (SAR) imagery for anomalies and potential oil slicks.</p>
      </header>

      <div className="content-card">
        <ErrorBoundary label="Detection">
          <DetectionPanel
            detection={detection}
            busy={detecting}
            method={method}
            unetAvailable={true}
            onRun={runDetect}
            onFocusLookalike={onFocusLookalike}
          />
        </ErrorBoundary>
      </div>
    </div>
  );
}
