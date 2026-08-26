import { useSpillState } from "../context/SpillContext";
import EvidencePanel from "../components/EvidencePanel";
import ErrorBoundary from "../components/ErrorBoundary";
import { ViewModeProvider } from "../lib/viewMode";

export default function Reports() {
  const { caseMeta, steps, report, reporting, detection, runReport, viewMode } = useSpillState();

  return (
    <ViewModeProvider value={viewMode}>
      <div className="page-shell">
        <header className="page-header">
          <h2>Investigation Reports</h2>
          <p>Compile evidence and generate a comprehensive, auditable incident report.</p>
        </header>

        <div className="content-card">
          <ErrorBoundary label="Evidence">
            <EvidencePanel
              caseMeta={caseMeta}
              steps={steps}
              report={report}
              busy={reporting}
              disabled={!detection}
              onGenerate={runReport}
            />
          </ErrorBoundary>
        </div>
      </div>
    </ViewModeProvider>
  );
}
