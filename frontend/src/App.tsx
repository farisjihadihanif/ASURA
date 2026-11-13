import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import LoginPage from "./pages/LoginPage";
import StudentChatPage from "./pages/StudentChatPage";
import LecturerApprovalsPage from "./pages/LecturerApprovalsPage";
import VerifySuratPage from "./pages/VerifySuratPage";

const HomeRedirect: React.FC = () => {
  const { user, isAuthenticated, isLoading } = useAuth();
  if (isLoading) return null;
  if (!isAuthenticated || !user) return <Navigate to="/login" replace />;
  return (
    <Navigate to={user.role === "LECTURER" ? "/approvals" : "/chat"} replace />
  );
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/verify" element={<VerifySuratPage />} />
          <Route path="/verify/:token" element={<VerifySuratPage />} />

          <Route
            path="/chat"
            element={
              <ProtectedRoute allowedRoles={["STUDENT"]}>
                <StudentChatPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/chat/:threadId"
            element={
              <ProtectedRoute allowedRoles={["STUDENT"]}>
                <StudentChatPage />
              </ProtectedRoute>
            }
          />

          <Route
            path="/approvals"
            element={
              <ProtectedRoute allowedRoles={["LECTURER", "STAFF", "ADMIN"]}>
                <LecturerApprovalsPage />
              </ProtectedRoute>
            }
          />

          <Route path="*" element={<HomeRedirect />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
};

export default App;
