import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";
import { useEventStream } from "./hooks/useEventStream";
import { Sidebar } from "./components/Layout/Sidebar";
import { Header } from "./components/Layout/Header";
import { LivePage } from "./pages/LivePage";
import { TracesPage } from "./pages/TracesPage";
import { EvalsPage } from "./pages/EvalsPage";
import { AdminPage } from "./pages/AdminPage";
import { LoginPage } from "./pages/LoginPage";

export default function App() {
  const auth = useAuth();

  // Open the live gRPC-Web stream as soon as we have a token
  useEventStream(auth.token);

  if (!auth.isAuthenticated) {
    return <LoginPage onLogin={auth.login} />;
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Header email={auth.email} role={auth.role} onLogout={auth.logout} />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto p-6">
          <Routes>
            <Route path="/" element={<LivePage />} />
            <Route path="/traces" element={<TracesPage />} />
            <Route path="/evals" element={<EvalsPage />} />
            <Route path="/admin" element={<AdminPage role={auth.role} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
