"use client";

import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { clp, type SeriesPoint } from "@/lib/api";

const COLORS = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"];

export function PriceChart({
  series,
  stores,
  min90,
}: {
  series: SeriesPoint[];
  stores: { slug: string; name: string }[];
  min90?: number;
}) {
  return (
    <div style={{ width: "100%", height: 320 }}>
      <ResponsiveContainer>
        <LineChart data={series} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="day"
            tickFormatter={(d: string) => d.slice(5)}
            stroke="var(--muted)"
            fontSize={12}
            minTickGap={24}
          />
          <YAxis
            stroke="var(--muted)"
            fontSize={12}
            width={70}
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => clp(v)}
          />
          <Tooltip
            formatter={(v) => clp(Number(v))}
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8 }}
          />
          <Legend />
          {min90 !== undefined && (
            <ReferenceLine y={min90} stroke="var(--good)" strokeDasharray="4 4" label={{ value: "mín. 90d", fill: "var(--good)", fontSize: 11, position: "insideBottomLeft" }} />
          )}
          {stores.map((s, i) => (
            <Line
              key={s.slug}
              type="stepAfter"
              dataKey={s.slug}
              name={s.name}
              stroke={COLORS[i % COLORS.length]}
              dot={false}
              strokeWidth={2}
              connectNulls
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
