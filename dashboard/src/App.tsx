import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { useAuthStore } from "./store/authStore";
// import { AgentsPage } from "./pages/AgentsPage"; // page removed from the dashboard (Option C: agents run in background)
import { ChargebackPage } from "./pages/ChargebackPage";
import { CostModelPage } from "./pages/CostModelPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DemoTourPage } from "./pages/DemoTourPage";
import { DriftPage } from "./pages/DriftPage";
import { ExperimentsPage } from "./pages/ExperimentsPage";
import { InvestigationDetailPage } from "./pages/InvestigationDetailPage";
import { LegalPage } from "./pages/LegalPage";
import { LoginPage } from "./pages/LoginPage";
import { ReturnRiskPage } from "./pages/ReturnRiskPage";
import { ReviewQueuePage } from "./pages/ReviewQueuePage";
import { SimulatorPage } from "./pages/SimulatorPage";
import { SupportPage } from "./pages/SupportPage";
import { Track2CompliancePage } from "./pages/Track2CompliancePage";
import { TransactionsPage } from "./pages/TransactionsPage";

function isAuthenticated() {
  return useAuthStore((s) => Boolean(s.token));
}

function ProtectedArea() {
  const authed = isAuthenticated();
  const location = useLocation();
  if (!authed) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <Outlet />;
}

function GuestArea() {
  const authed = isAuthenticated();
  if (authed) {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<GuestArea />}>
          <Route path="/login" element={<LoginPage />} />
        </Route>
        <Route element={<ProtectedArea />}>
          <Route element={<AppShell />}>
            <Route path="/" element={<Navigate to="/cost-model" replace />} />
            {/* Track 2 is return-risk. Fraud/chargeback routes are kept in
                code but commented out of the primary surface (still reachable
                by URL via the catch-all redirect to /return-risk). */}
            {/* <Route path="/fraud" element={<DashboardPage />} /> */}
            {/* <Route path="/chargeback" element={<ChargebackPage />} /> */}
            <Route path="/return-risk" element={<ReturnRiskPage />} />
            <Route path="/transactions" element={<TransactionsPage />} />
            <Route path="/cost-model" element={<CostModelPage />} />
            <Route path="/drift" element={<DriftPage />} />
            <Route path="/experiments" element={<ExperimentsPage />} />
            {/* <Route path="/agents" element={<AgentsPage />} /> page removed — worker runs in background */}
            <Route path="/track2-compliance" element={<Track2CompliancePage />} />
            <Route path="/demo-tour" element={<DemoTourPage />} />
            <Route path="/review-queue" element={<ReviewQueuePage />} />
            <Route path="/simulator" element={<SimulatorPage />} />
            <Route path="/support" element={<SupportPage />} />
            <Route path="/legal/:slug" element={<LegalPage />} />
            <Route path="/investigation/:txnId" element={<InvestigationDetailPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;