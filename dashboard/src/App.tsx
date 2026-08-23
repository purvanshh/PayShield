import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { DashboardPage } from "./pages/DashboardPage";
import { InvestigationDetailPage } from "./pages/InvestigationDetailPage";
import { LoginPage } from "./pages/LoginPage";
import { ReturnRiskPage } from "./pages/ReturnRiskPage";
import { ChargebackPage } from "./pages/ChargebackPage";

function App() {
  return (
    <BrowserRouter>
      <nav style={{ padding: "0 24px", display: "flex", gap: 16 }}>
        <Link to="/">Fraud</Link>
        <Link to="/return-risk">Return Risk</Link>
        <Link to="/chargeback">Chargeback</Link>
        <Link to="/login">Login</Link>
      </nav>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/return-risk" element={<ReturnRiskPage />} />
        <Route path="/chargeback" element={<ChargebackPage />} />
        <Route path="/investigation/:txnId" element={<InvestigationDetailPage />} />
        <Route path="/login" element={<LoginPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
