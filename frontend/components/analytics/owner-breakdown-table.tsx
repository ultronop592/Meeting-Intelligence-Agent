"use client";

import { UserCheck, AlertCircle } from "lucide-react";
import type { ActionItemOwnerBreakdown } from "@/types/api";

interface OwnerBreakdownTableProps {
  owners?: ActionItemOwnerBreakdown[];
  isLoading?: boolean;
}

export function OwnerBreakdownTable({ owners = [], isLoading }: OwnerBreakdownTableProps) {
  if (isLoading) {
    return (
      <div className="h-64 animate-pulse rounded-[16px] border border-border bg-surface p-4" />
    );
  }

  return (
    <div className="rounded-[16px] border border-border bg-surface p-5 shadow-xs">
      <div className="pb-4 border-b border-border/60 flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <UserCheck className="h-4 w-4 text-foreground" />
            Action Item Load per Owner
          </h3>
          <p className="text-xs text-text-tertiary mt-0.5">
            Individual task distribution, completion, and overdue metrics
          </p>
        </div>
      </div>

      {owners.length === 0 ? (
        <div className="flex h-36 flex-col items-center justify-center text-center text-sm text-text-tertiary">
          No owner breakdown available.
        </div>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-border text-text-tertiary uppercase tracking-wider font-medium text-[10px]">
                <th className="py-2.5 px-3">Owner</th>
                <th className="py-2.5 px-3 text-center">Open</th>
                <th className="py-2.5 px-3 text-center">In Progress</th>
                <th className="py-2.5 px-3 text-center">Done</th>
                <th className="py-2.5 px-3 text-center">Overdue</th>
                <th className="py-2.5 px-3 text-right">Total</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60 text-foreground font-medium">
              {owners.map((row, idx) => (
                <tr key={idx} className="hover:bg-surface-2/40 transition-colors">
                  <td className="py-3 px-3 font-semibold text-foreground flex items-center gap-2">
                    <div className="h-6 w-6 rounded-full bg-surface-2 border border-border flex items-center justify-center text-[10px] uppercase font-bold text-text-secondary">
                      {row.owner.slice(0, 2)}
                    </div>
                    {row.owner}
                  </td>
                  <td className="py-3 px-3 text-center text-blue-600 font-semibold">{row.open}</td>
                  <td className="py-3 px-3 text-center text-amber-600 font-semibold">{row.in_progress}</td>
                  <td className="py-3 px-3 text-center text-emerald-600 font-semibold">{row.done}</td>
                  <td className="py-3 px-3 text-center">
                    {row.overdue > 0 ? (
                      <span className="inline-flex items-center gap-1 rounded-md bg-danger/10 px-2 py-0.5 text-danger font-bold">
                        <AlertCircle className="h-3 w-3" />
                        {row.overdue}
                      </span>
                    ) : (
                      <span className="text-text-tertiary">0</span>
                    )}
                  </td>
                  <td className="py-3 px-3 text-right font-bold text-foreground">{row.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
