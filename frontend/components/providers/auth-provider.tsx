"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import {
  User,
  getStoredToken,
  getStoredUser,
  getMeApi,
  clearStoredSession,
  loginApi,
  registerApi,
  LoginPayload,
  RegisterPayload,
} from "@/lib/api/auth";

type AuthContextType = {
  user: User | null;
  loading: boolean;
  login: (payload: LoginPayload) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const PUBLIC_PATHS = ["/login", "/register"];

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    async function initAuth() {
      const token = getStoredToken();
      const cachedUser = getStoredUser();

      if (!token) {
        setUser(null);
        setLoading(false);
        if (!PUBLIC_PATHS.includes(pathname)) {
          router.push("/login");
        }
        return;
      }

      if (cachedUser) {
        setUser(cachedUser);
      }

      try {
        const currentUser = await getMeApi();
        setUser(currentUser);
      } catch (err) {
        clearStoredSession();
        setUser(null);
        if (!PUBLIC_PATHS.includes(pathname)) {
          router.push("/login");
        }
      } finally {
        setLoading(false);
      }
    }

    initAuth();
  }, [pathname, router]);

  const handleLogin = async (payload: LoginPayload) => {
    setLoading(true);
    try {
      const res = await loginApi(payload);
      setUser(res.user);
      router.push("/dashboard");
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (payload: RegisterPayload) => {
    setLoading(true);
    try {
      const res = await registerApi(payload);
      setUser(res.user);
      router.push("/dashboard");
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    clearStoredSession();
    setUser(null);
    router.push("/login");
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login: handleLogin,
        register: handleRegister,
        logout: handleLogout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
