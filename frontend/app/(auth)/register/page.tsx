"use client";

import { useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Lock, Mail, User, ArrowRight, Sparkles, AlertCircle, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function RegisterPage() {
  const { register } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email.trim() || !password) {
      setError("Please fill in all required fields.");
      return;
    }

    if (password.length < 6) {
      setError("Password must be at least 6 characters long.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setSubmitting(true);
    try {
      await register({
        email: email.trim(),
        password,
        full_name: fullName.trim() || undefined,
      });
      toast.success("Account created!", {
        description: "Welcome to Meeting Intelligence AI.",
      });
    } catch (err: any) {
      const msg = err?.message || "Failed to create account. Please try again.";
      setError(msg);
      toast.error("Registration failed", { description: msg });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Brand Header */}
      <div className="flex flex-col items-center text-center">
        <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-accent/15 text-accent shadow-inner border border-accent/20">
          <Sparkles className="h-6 w-6 animate-pulse" />
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Create Account</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Join Meeting Intelligence AI to streamline your meetings
        </p>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="flex items-center gap-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-text-secondary" htmlFor="fullName">
            Full Name (Optional)
          </label>
          <div className="relative flex items-center">
            <User className="absolute left-3 h-4 w-4 text-text-tertiary" />
            <input
              id="fullName"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Alex Johnson"
              className="w-full rounded-xl border border-border bg-surface-2 py-2.5 pl-9 pr-4 text-sm text-foreground outline-none transition-all placeholder:text-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent"
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-text-secondary" htmlFor="email">
            Email Address *
          </label>
          <div className="relative flex items-center">
            <Mail className="absolute left-3 h-4 w-4 text-text-tertiary" />
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="alex@company.com"
              className="w-full rounded-xl border border-border bg-surface-2 py-2.5 pl-9 pr-4 text-sm text-foreground outline-none transition-all placeholder:text-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent"
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-text-secondary" htmlFor="password">
            Password *
          </label>
          <div className="relative flex items-center">
            <Lock className="absolute left-3 h-4 w-4 text-text-tertiary" />
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full rounded-xl border border-border bg-surface-2 py-2.5 pl-9 pr-4 text-sm text-foreground outline-none transition-all placeholder:text-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent"
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-text-secondary" htmlFor="confirmPassword">
            Confirm Password *
          </label>
          <div className="relative flex items-center">
            <Lock className="absolute left-3 h-4 w-4 text-text-tertiary" />
            <input
              id="confirmPassword"
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full rounded-xl border border-border bg-surface-2 py-2.5 pl-9 pr-4 text-sm text-foreground outline-none transition-all placeholder:text-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent"
            />
          </div>
        </div>

        <Button
          type="submit"
          disabled={submitting}
          className="mt-2 w-full py-2.5 font-medium text-sm transition-all"
        >
          {submitting ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Creating account...
            </>
          ) : (
            <>
              Get Started <ArrowRight className="ml-2 h-4 w-4" />
            </>
          )}
        </Button>
      </form>

      {/* Footer link */}
      <div className="text-center text-xs text-text-tertiary">
        Already have an account?{" "}
        <Link href="/login" className="font-semibold text-accent hover:underline">
          Sign in
        </Link>
      </div>
    </div>
  );
}
