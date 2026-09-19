import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout";
import Overview from "./pages/Overview";
import Placeholder from "./pages/Placeholder";
import { SpillProvider } from "./context/SpillContext";
import MaritimeMap from "./pages/MaritimeMap";
import SatelliteIntelligence from "./pages/SatelliteIntelligence";
import VesselIntelligence from "./pages/VesselIntelligence";
import DriftIntelligence from "./pages/DriftIntelligence";
import Attribution from "./pages/Attribution";
import RerouteSimulation from "./pages/RerouteSimulation";
import Reports from "./pages/Reports";
import DataSources from "./pages/DataSources";
import Alerts from "./pages/Alerts";

export default function App() {
  return (
    <SpillProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<AppLayout />}>
            <Route index element={<Overview />} />
            <Route path="incidents" element={<Placeholder title="Incident Investigation" />} />
            <Route path="map" element={<MaritimeMap />} />
            <Route path="satellite" element={<SatelliteIntelligence />} />
            <Route path="vessel" element={<VesselIntelligence />} />
            <Route path="drift" element={<DriftIntelligence />} />
            <Route path="attribution" element={<Attribution />} />
            <Route path="reroute" element={<RerouteSimulation />} />
            <Route path="reports" element={<Reports />} />
            <Route path="alerts" element={<Alerts />} />
            <Route path="data" element={<DataSources />} />
            <Route path="models" element={<Placeholder title="Models" />} />
            <Route path="settings" element={<Placeholder title="Settings" />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </SpillProvider>
  );
}
