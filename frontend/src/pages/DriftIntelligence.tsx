import { useSpillState } from "../context/SpillContext";
import DriftControls from "../components/DriftControls";
import ErrorBoundary from "../components/ErrorBoundary";

export default function DriftIntelligence() {
  const {
    hindcast,
    forecast,
    drifting,
    hindcastPlaying,
    hindcastIndex,
    frames,
    runHindcast,
    runForecast,
    setHindcastIndex,
    setHindcastPlaying,
  } = useSpillState();

  return (
    <div className="page-shell">
      <header className="page-header">
        <h2>Drift Intelligence</h2>
        <p>Compute particle drift backwards (hindcast) to estimate origin, or forwards (forecast) to predict spread.</p>
      </header>

      <div className="content-card">
        <ErrorBoundary label="Drift">
          <DriftControls
            hindcast={hindcast}
            forecast={forecast}
            busy={drifting}
            playing={hindcastPlaying}
            frameIndex={hindcastIndex}
            frameCount={frames}
            onHindcast={runHindcast}
            onForecast={runForecast}
            onScrub={(i) => { setHindcastPlaying(false); setHindcastIndex(i); }}
            onTogglePlay={() => {
              if (!hindcastPlaying && hindcastIndex >= frames - 1) setHindcastIndex(0);
              setHindcastPlaying(p => !p);
            }}
          />
        </ErrorBoundary>
      </div>
    </div>
  );
}
