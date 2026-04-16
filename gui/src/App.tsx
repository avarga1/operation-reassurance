import { Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Overview } from "@/pages/Overview";
import { Coverage } from "@/pages/Coverage";
import { Observability } from "@/pages/Observability";
import { Solid } from "@/pages/Solid";
import { BlastRadius } from "@/pages/BlastRadius";
import { Develop } from "@/pages/Develop";
import { Settings } from "@/pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/overview" replace />} />
        <Route path="overview" element={<Overview />} />
        <Route path="coverage" element={<Coverage />} />
        <Route path="observability" element={<Observability />} />
        <Route path="solid" element={<Solid />} />
        <Route path="blast-radius" element={<BlastRadius />} />
        <Route path="develop" element={<Develop />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
