import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { NewAnalysisModal } from "./NewAnalysisModal";
import { ReturnRiskFormModal } from "./ReturnRiskFormModal";
import { NotificationsButton } from "./Notifications";
import { useAuthStore } from "../store/authStore";

// Track 2 is return-risk. Fraud and chargeback are out-of-scope extensions:
// their routes stay reachable by URL but are hidden from the primary nav.
const SECTION_LINKS: { to: string; label: string; end: boolean }[] = [
  // { to: "/fraud", label: "Fraud", end: false },
  // { to: "/chargeback", label: "Chargeback", end: false },
];

const OPERATIONS = [
  { to: "/cost-model", label: "Cost Model", icon: "calculate", end: false },
  { to: "/return-risk", label: "Return Risk", icon: "receipt_long", end: false },
  { to: "/drift", label: "Drift Monitor", icon: "monitoring", end: false },
  { to: "/experiments", label: "A/B Experiments", icon: "science", end: false },
  // { to: "/agents", label: "Agents", icon: "psychology", end: false }, // page removed — agents run in background
  { to: "/review-queue", label: "Review Queue", icon: "task_alt", end: false },
  { to: "/simulator", label: "Simulator", icon: "tune", end: false },
  { to: "/track2-compliance", label: "Track 2 Compliance", icon: "fact_check", end: false },
];

const LEGAL_LINKS = [
  { to: "/legal/privacy", label: "Privacy Policy" },
  { to: "/legal/terms", label: "Terms of Service" },
  { to: "/legal/security", label: "Security Disclosure" },
  { to: "/legal/regulatory", label: "Regulatory Info" },
];

function SidebarNavItem({
  to,
  label,
  icon,
  end,
}: {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `flex items-center gap-x-4 py-3 pl-6 transition-all duration-200 ${
          isActive
            ? "text-primary font-bold border-l-2 border-primary pl-[22px] bg-white/5"
            : "text-on-surface-variant hover:bg-white/5 hover:text-primary"
        }`
      }
    >
      <span className="material-symbols-outlined text-[20px]">{icon}</span>
      <span className="font-label-caps text-label-caps">{label}</span>
    </NavLink>
  );
}

export function AppShell() {
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [returnRiskFormOpen, setReturnRiskFormOpen] = useState(false);

  const signOut = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen flex flex-col md:flex-row relative bg-background text-on-surface">
      <div className="noise-overlay" aria-hidden />

      {/* Mobile top bar */}
      <nav className="md:hidden fixed top-0 inset-x-0 z-50 flex justify-between items-center px-container-padding-mobile h-20 bg-surface/80 backdrop-blur-md border-b border-white/10">
        <div className="font-display-lg-mobile text-display-lg-mobile font-bold text-primary tracking-tight">
          PayShield
        </div>
        <div className="flex gap-4 items-center">
          <NotificationsButton />
        </div>
      </nav>

      {/* Desktop sidebar */}
      <aside className="hidden md:flex flex-col h-screen sticky top-0 w-64 shrink-0 py-8 bg-surface-container-low border-r border-white/10 z-10">
        <div className="px-gutter mb-8">
          <h1 className="font-display-lg-mobile text-display-lg-mobile text-primary leading-tight">
            PayShield
          </h1>
        </div>

        {/* New Analysis */}
        <div className="px-gutter mb-6 flex flex-col gap-3">
          <button
            onClick={() => setAnalysisOpen(true)}
            className="w-full bg-primary text-on-primary font-label-caps text-label-caps py-3 px-4 uppercase hover:bg-primary-container transition-colors duration-300"
          >
            New Analysis
          </button>
          <button
            onClick={() => navigate("/demo-tour")}
            className="w-full border border-primary text-primary font-label-caps text-label-caps py-3 px-4 uppercase hover:bg-primary/10 transition-colors duration-300"
          >
            Start Demo
          </button>
        </div>

        <nav className="flex-1 flex flex-col gap-y-2 overflow-y-auto">
          <p className="px-gutter mb-1 font-label-caps text-label-caps text-outline uppercase">
            Operations
          </p>
          {OPERATIONS.map((item) => (
            <SidebarNavItem
              key={item.to}
              to={item.to}
              label={item.label}
              icon={item.icon}
              end={item.end}
            />
          ))}

          <p className="px-gutter mt-6 mb-1 font-label-caps text-label-caps text-outline uppercase">
            Help
          </p>
          <SidebarNavItem to="/support" label="Support" icon="help_outline" />
          <button
            onClick={signOut}
            className="flex items-center gap-x-4 py-3 pl-6 text-on-surface-variant hover:bg-white/5 hover:text-error transition-colors duration-300 text-left cursor-pointer"
          >
            <span className="material-symbols-outlined text-[20px]">logout</span>
            <span className="font-label-caps text-label-caps">Sign Out</span>
          </button>
        </nav>
      </aside>

      {/* Main column */}
      <div className="flex-1 flex flex-col min-w-0">
        <main className="flex-1 px-container-padding-mobile md:px-container-padding-desktop py-12 max-w-7xl mx-auto w-full">
          <Outlet />
        </main>

        {/* Footer */}
        <footer className="w-full px-container-padding-mobile md:px-container-padding-desktop flex flex-col md:flex-row justify-between items-center max-w-7xl mx-auto border-t border-white/10 py-10 mt-auto">
          <div className="font-display-lg-mobile text-display-lg-mobile text-on-surface mb-6 md:mb-0">
            PayShield
          </div>
          <div className="flex flex-wrap justify-center gap-6 mb-6 md:mb-0">
            {LEGAL_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className="text-outline font-label-caps text-label-caps uppercase tracking-widest hover:text-primary transition-colors duration-300"
              >
                {link.label}
              </NavLink>
            ))}
          </div>
          <div className="text-outline font-body-md text-body-md text-sm">
            © 2026 PayShield Institutional. All rights reserved.
          </div>
        </footer>
      </div>

      {/* Mobile bottom nav */}
      <div className="md:hidden fixed bottom-0 inset-x-0 bg-surface/90 backdrop-blur-md border-t border-white/10 flex justify-around items-center h-16 z-50">
        {SECTION_LINKS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-1 pt-1 ${
                isActive ? "text-primary" : "text-on-surface-variant"
              }`
            }
          >
            <span className="material-symbols-outlined text-[20px]">
              {item.to === "/fraud" ? "grid_view" : item.to === "/return-risk" ? "receipt_long" : "shield"}
            </span>
          </NavLink>
        ))}
        <NavLink
          to="/support"
          className={({ isActive }) =>
            `flex flex-1 flex-col items-center gap-1 pt-1 ${
              isActive ? "text-primary" : "text-on-surface-variant"
            }`
          }
        >
          <span className="material-symbols-outlined text-[20px]">help_outline</span>
        </NavLink>
      </div>

      <NewAnalysisModal
        open={analysisOpen}
        onClose={() => setAnalysisOpen(false)}
        onStartReturnRisk={() => setReturnRiskFormOpen(true)}
      />
      <ReturnRiskFormModal
        open={returnRiskFormOpen}
        onClose={() => setReturnRiskFormOpen(false)}
      />
    </div>
  );
}