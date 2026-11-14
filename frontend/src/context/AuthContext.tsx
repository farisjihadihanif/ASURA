import React, { createContext, useContext, useEffect, useState } from "react";
import authService from "../services/authService";
import type { RegisterPayload } from "../services/authService";
import type { User } from "../types";

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (nip_nim: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  switchAccount: (nip_nim: string) => Promise<void>;
  addAccount: () => void;
  register: (payload: RegisterPayload) => Promise<User>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [user, setUser] = useState<User | null>(() =>
    authService.getCurrentUser(),
  );
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const refreshUser = async () => {
    const token = authService.getToken();
    if (!token) {
      setUser(null);
      return;
    }
    try {
      const freshUser = await authService.getMe();
      setUser(freshUser);
    } catch {
      setUser(null);
    }
  };

  useEffect(() => {
    const init = async () => {
      await refreshUser();
      setIsLoading(false);
    };
    void init();
  }, []);

  const login = async (nip_nim: string, password: string): Promise<User> => {
    const res = await authService.login(nip_nim, password);
    const fullUser = await authService.getMe().catch(() => res.user);
    setUser(fullUser);
    return fullUser;
  };

  const logout = async () => {
    await authService.logout();
    setUser(null);
  };

  const goHome = (u: User) => {
    window.location.assign(u.role === "LECTURER" ? "/approvals" : "/chat");
  };

  const switchAccount = async (nip_nim: string) => {
    const next = await authService.switchTo(nip_nim);
    if (next) {
      goHome(next);
    } else {
      setUser(null);
      window.location.assign("/login");
    }
  };

  const register = async (payload: RegisterPayload): Promise<User> => {
    const res = await authService.register(payload);
    setUser(res.user);
    goHome(res.user);
    return res.user;
  };

  const addAccount = () => {
    authService.addAccount();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: Boolean(user && authService.getToken()),
        isLoading,
        login,
        logout,
        switchAccount,
        addAccount,
        register,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth harus digunakan di dalam AuthProvider.");
  return ctx;
}
