import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './shared/Layout';
import { DiscoverPage } from './features/discover/DiscoverPage';
import { ScenarioPage } from './features/scenarios/ScenarioPage';
import { OnboardingPage } from './features/form/OnboardingPage';
import { ComingSoonPage, WelcomePage } from './features/misc/Pages';
import { ComparePage } from './features/compare/ComparePage';
import { ReportPage } from './features/reports/ReportPage';
import { DebugPage } from './features/debug/DebugPage';

export default function App() {
  return (
    <Routes>
      <Route path="/welcome" element={<WelcomePage />} />
      <Route path="/onboarding" element={<OnboardingPage />} />

      <Route element={<Layout />}>
        <Route index element={<DiscoverPage />} />
        <Route path="discover" element={<Navigate to="/" replace />} />
        <Route path="scenarios" element={<ScenarioPage />} />
        <Route path="compare" element={<ComparePage />} />
        <Route path="reports" element={<ReportPage />} />
        <Route path="debug" element={<DebugPage />} />
        <Route
          path="settings"
          element={<ComingSoonPage title="Settings" text="Display, privacy and data preferences will be managed here." />}
        />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
