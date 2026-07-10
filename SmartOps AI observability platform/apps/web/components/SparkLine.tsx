"use client";
import { Area, AreaChart, ResponsiveContainer, Tooltip } from "recharts";

interface Props {
  data: { value: number }[];
  color?: string;
}

export default function SparkLine({ data, color = "#3b82f6" }: Props) {
  const gradientId = `sg-${color.replace("#", "")}`;
  return (
    <ResponsiveContainer width="100%" height={44}>
      <AreaChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor={color} stopOpacity={0.25} />
            <stop offset="95%" stopColor={color} stopOpacity={0}    />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={1.5}
          fill={`url(#${gradientId})`}
          dot={false}
          isAnimationActive={false}
        />
        <Tooltip
          contentStyle={{
            background: "#1f2937",
            border: "1px solid #374151",
            borderRadius: 6,
            fontSize: 11,
            color: "#f9fafb",
            padding: "4px 8px",
          }}
          formatter={(v: number) => [v.toFixed(1), ""]}
          labelFormatter={() => ""}
          cursor={{ stroke: "#4b5563", strokeWidth: 1 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
