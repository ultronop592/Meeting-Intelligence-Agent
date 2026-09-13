"use client";

import { Toaster } from "sonner";
import { useTheme } from "@/components/providers/theme-provider";

export function ToastProvider() {
  const { theme } = useTheme();
  return <Toaster position="top-right" richColors theme={theme} />;
}
