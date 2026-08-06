"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ParticipantAnalyticsItem } from "@/types/api";

interface ParticipantActivityChartProps {
  participants?: ParticipantAnalyticsItem[];
  isLoading?: boolean;
}

export function ParticipantActivityChart({
  participants = [],
  isLoading,
}: ParticipantActivityChartProps) {
  if (isLoading) {
    return (
      <div className="h-80 animate-pulse rounded-[16px] border border-border bg-surface p-4" />
    );
  }

  const topParticipants = participants.slice(0, 8);

  return (
    <div className="rounded-[16px] border border-border bg-surface p-5 shadow-xs">
      <div className="pb-4 border-b border-border/60">
        <h3 className="text-base font-semibold text-foreground">
          Participant Leaderboard
        </h3>
        <p className="text-xs text-text-tertiary mt-0.5">
          Meeting attendance vs. action items load per participant
        </p>
      </div>

      {topParticipants.length === 0 ? (
        <div className="flex h-56 flex-col items-center justify-center text-center text-sm text-text-tertiary">
          No participant data available yet.
        </div>
      ) : (
        <div className="mt-4 h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={topParticipants}
              margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E5E5" />
              <XAxis
                dataKey="name"
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11, fill: "#7A7A7A" }}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11, fill: "#7A7A7A" }}
                allowDecimals={false}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#FFFFFF",
                  borderColor: "#E5E5E5",
                  borderRadius: "12px",
                  fontSize: "12px",
                  boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
                }}
              />
              <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "8px" }} />
              <Bar
                dataKey="meetings_count"
                name="Meetings Attended"
                fill="#1C1C1C"
                radius={[6, 6, 0, 0]}
                barSize={20}
              />
              <Bar
                dataKey="action_items_count"
                name="Actions Assigned"
                fill="#FF9F43"
                radius={[6, 6, 0, 0]}
                barSize={20}
              />
              <Bar
                dataKey="completed_action_items"
                name="Actions Done"
                fill="#10B981"
                radius={[6, 6, 0, 0]}
                barSize={20}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
