import { useSpillState } from "../context/SpillContext";
import VesselTable from "../components/VesselTable";
import ScoreBreakdown from "../components/ScoreBreakdown";
import ErrorBoundary from "../components/ErrorBoundary";

export default function Attribution() {
  const { attribution, attributing, hindcast, selectedMmsi, runAttribute, setSelectedMmsi } = useSpillState();
  const selectedCandidate = attribution?.candidates.find((c) => c.mmsi === selectedMmsi) ?? null;

  return (
    <div className="page-shell">
      <header className="page-header">
        <h2>Vessel Attribution</h2>
        <p>Correlate the estimated spill origin with historical AIS data to identify candidate vessels.</p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 content-card">
          <ErrorBoundary label="Attribution">
            <VesselTable
              attribution={attribution}
              busy={attributing}
              disabled={!hindcast}
              selectedMmsi={selectedMmsi}
              onRun={runAttribute}
              onSelect={setSelectedMmsi}
            />
          </ErrorBoundary>
        </div>

        <div className="lg:col-span-1 content-card">
          <ErrorBoundary label="Score breakdown">
            <ScoreBreakdown
              candidate={selectedCandidate}
              weights={attribution?.weights ?? null}
              provenance={attribution?.provenance}
            />
          </ErrorBoundary>
        </div>
      </div>
    </div>
  );
}
