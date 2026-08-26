import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout";
import Overview from "./pages/Overview";
import MaritimeMap from "./pages/MaritimeMap";
import Placeholder from "./pages/Placeholder";
import { SpillProvider } from "./context/SpillContext";
import SatelliteIntelligence from "./pages/SatelliteIntelligence";
import DriftIntelligence from "./pages/DriftIntelligence";
import Attribution from "./pages/Attribution";
import Reports from "./pages/Reports";

export default function App() {
  return (
    <SpillProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<AppLayout />}>
            <Route index element={<Overview />} />
            <Route path="incidents" element={<Placeholder title="Incident Investigation" />} />
            <Route path="map" element={<div />} />
            <Route path="satellite" element={<SatelliteIntelligence />} />
            <Route path="vessel" element={<Placeholder title="Vessel Intelligence" />} />
            <Route path="drift" element={<DriftIntelligence />} />
            <Route path="attribution" element={<Attribution />} />
            <Route path="reports" element={<Reports />} />
            <Route path="alerts" element={<Placeholder title="Alerts" />} />
            <Route path="data" element={<Placeholder title="Data Sources" />} />
            <Route path="models" element={<Placeholder title="Models" />} />
            <Route path="settings" element={<Placeholder title="Settings" />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </SpillProvider>
  );
}
