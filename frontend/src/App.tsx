import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { AssetClassesPage } from "./pages/AssetClassesPage";
import { BackupsPage } from "./pages/BackupsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { FinanceExpensesPage } from "./pages/FinanceExpensesPage";
import { FinanceIncomePage } from "./pages/FinanceIncomePage";
import { FinanceInvestmentsPage } from "./pages/FinanceInvestmentsPage";
import { FinanceSummaryPage } from "./pages/FinanceSummaryPage";
import { FinanceTransfersPage } from "./pages/FinanceTransfersPage";
import { HoldingsPage } from "./pages/HoldingsPage";
import { LoginPage } from "./pages/LoginPage";
import { OpenFinancePage } from "./pages/OpenFinancePage";
import { OtherInvestmentsPage } from "./pages/OtherInvestmentsPage";
import { RebalancePage } from "./pages/RebalancePage";
import { SnapshotDetailPage, SnapshotsPage } from "./pages/SnapshotsPage";

function SnapshotDetailRoute() {
  const { snapshotId } = useParams();
  if (!snapshotId) return <Navigate to="/history" replace />;
  return <SnapshotDetailPage snapshotId={snapshotId} />;
}

export function App() {
  return (
    <Routes>
      <Route path="/auth/login" element={<LoginPage />} />
      <Route element={<AppShell />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/portfolio/holdings" element={<HoldingsPage />} />
        <Route path="/portfolio/investments" element={<OtherInvestmentsPage />} />
        <Route path="/allocation/classes" element={<AssetClassesPage />} />
        <Route path="/allocation/rebalance" element={<RebalancePage />} />
        <Route path="/finance/summary" element={<FinanceSummaryPage />} />
        <Route path="/finance/income" element={<FinanceIncomePage />} />
        <Route path="/finance/expenses" element={<FinanceExpensesPage />} />
        <Route path="/finance/transfers" element={<FinanceTransfersPage />} />
        <Route path="/finance/investments" element={<FinanceInvestmentsPage />} />
        <Route path="/history" element={<SnapshotsPage />} />
        <Route path="/history/:snapshotId" element={<SnapshotDetailRoute />} />
        <Route path="/backups" element={<BackupsPage />} />
        <Route path="/open-finance" element={<OpenFinancePage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
