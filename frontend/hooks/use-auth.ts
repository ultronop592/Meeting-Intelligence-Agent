"use client";

import { useState } from "react";

const TOKEN_KEY = "mia_token";

export function useAuth() {
  const [token, setToken] = useState<string>(() => {
    if (typeof window === "undefined") {
      return "";
    }

    return localStorage.getItem(TOKEN_KEY) || "";
  });

  const saveToken = (value: string) => {
    const normalized = value.trim();
    localStorage.setItem(TOKEN_KEY, normalized);
    document.cookie = `mia_token=${encodeURIComponent(normalized)}; path=/; SameSite=Lax`;
    setToken(normalized);
  };

  const clearToken = () => {
    localStorage.removeItem(TOKEN_KEY);
    document.cookie = "mia_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    setToken("");
  };

  return {
    token,
    isAuthenticated: Boolean(token),
    saveToken,
    clearToken,
  };
}
