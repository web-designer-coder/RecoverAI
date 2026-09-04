import { createFileRoute } from "@tanstack/react-router";
import { getAnalytics } from "@/lib/api";
import type { AnalyticsData } from "@/lib/types";
import { formatLakh, formatPct } from "@/lib/format";
import { PageLoading, EmptyState, ErrorState } from "@/components/states";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
} from "@/components/ui/chart";
import {
  AreaChart as RechartsAreaChart,
  Area as RechartsArea,
  BarChart as RechartsBarChart,
  Bar as RechartsBar,
  XAxis as RechartsXAxis,
  YAxis as RechartsYAxis,
  CartesianGrid as RechartsGrid,
  Tooltip as RechartsTooltip,
  Legend as RechartsLegend,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { useState, useEffect, Suspense } from "react";

export const Route = createFileRoute("/app/analytics")({
  head: () => ({
    meta: [
      { title: "Recovery Analytics — RecoverAI" },
      { name: "description", content: "Recovery rate trends, category performance and attempt-level effectiveness." },
      { property: "og:title", content: "Recovery Analytics — RecoverAI" },
      { property: "og:description", content: "Measure incremental revenue recovered versus static retries." },
    ],
  }),
  component: AnalyticsPage,
});

function AnalyticsPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="headline-md text-foreground">Analytics</h1>
        <p className="mt-1.5 text-[0.8125rem] text-muted-foreground">
          Recovery rate trends, category performance, and attempt-level effectiveness across your failure population.
        </p>
      </header>

      <AnalyticsCharts />
    </div>
  );
}

function AnalyticsCharts() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    getAnalytics()
      .then((d) => {
        if (alive) {
          setData(d);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (alive) {
          setError(err instanceof Error ? err.message : 'Failed to load analytics');
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <RecoveryRateChartSkeleton />
        <div className="grid gap-6 lg:grid-cols-2">
          <CategoryChartSkeleton />
          <MethodChartSkeleton />
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <AttemptChartSkeleton />
          <AvgTimeChartSkeleton />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <ErrorState
          title="Couldn't load analytics"
          copy={error}
          retry={() => {
            setError(null);
            setLoading(true);
            getAnalytics()
              .then((d) => { setData(d); setLoading(false); })
              .catch((err) => { setError(err instanceof Error ? err.message : 'Failed to load analytics'); setLoading(false); });
          }}
        />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-6">
        <EmptyState
          title="No analytics data"
          copy="Run a simulation or wait for recovery data to appear."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <RecoveryRateChart data={data.performance} />
      <div className="grid gap-6 lg:grid-cols-2">
        <CategoryChart data={data.byCategory} />
        <MethodChart data={data.byMethod} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <AttemptChart data={data.byAttempt} />
        <AvgTimeChart data={data.avgTimeToRecoveryHours} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Recovery Rate — Area Chart (Revenue vs Baseline)                   */
/* ------------------------------------------------------------------ */

function RecoveryRateChart({ data }: { data: AnalyticsData['performance'] }) {
  if (!data || data.length === 0) {
    return (
      <div className="rounded-xl bg-white/[0.03] p-6">
        <p className="label-sm text-faint">Recovery Rate — AI vs Static (%)</p>
        <EmptyState title="No performance data yet" copy="Run recoveries and check back — AI vs static comparison builds from your first settled recovery." />
      </div>
    );
  }

  const chartData = data.map((p) => {
    let formattedDate = 'Invalid Date';
    try {
      const dateObj = new Date(p.month + "-01T00:00:00");
      if (!isNaN(dateObj.getTime())) {
        formattedDate = dateObj.toLocaleDateString(undefined, { month: 'short', year: '2-digit' });
      }
    } catch {
      formattedDate = p.month;
    }
    return {
      date: formattedDate !== 'Invalid Date' ? formattedDate : p.month,
      ai: p.ai,
      static: p.static,
    };
  });

  return (
    <div className="rounded-xl bg-white/[0.03] p-6">
      <p className="label-sm text-faint">Recovery Rate — AI vs Static (%)</p>
      <ChartContainer
        config={{
          ai: { label: "RecoverAI", color: "var(--chart-1)" },
          static: { label: "Static Retry", color: "var(--chart-2)" },
        }}
        className="mt-6 aspect-video"
      >
        <ResponsiveContainer width="100%" height="100%">
          <RechartsAreaChart data={chartData} margin={{ top: 20, right: 40, bottom: 40, left: 50 }}>
            <defs>
              <linearGradient id="area-gradient-ai" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--chart-1)" stopOpacity="0.25" />
                <stop offset="100%" stopColor="var(--chart-1)" stopOpacity="0" />
              </linearGradient>
              <linearGradient id="area-gradient-static" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--chart-2)" stopOpacity="0.15" />
                <stop offset="100%" stopColor="var(--chart-2)" stopOpacity="0" />
              </linearGradient>
            </defs>
            <RechartsGrid stroke="rgb(255 255 255 / 0.06)" strokeOpacity={1} />
            <RechartsXAxis
              dataKey="date"
              tick={{ stroke: "#555b69", fontSize: 11 }}
            />
            <RechartsYAxis
              tickFormatter={(v) => `${v}%`}
              tick={{ stroke: "#555b69", fontSize: 11 }}
              tickCount={5}
            />
            <RechartsTooltip
              content={<ChartTooltipContent
                indicator="dot"
                nameKey="date"
                labelFormatter={(date) => `Month: ${date}`}
                // @ts-expect-error - Recharts Formatter type mismatch, but runtime works correctly
                formatter={(value: number, name: string, _item: any, _index: number, _payload: any[]) => [
                  `${value.toFixed(1)}%`,
                  name === 'ai' ? 'RecoverAI' : 'Static Retry',
                ]}
              />}
            />
            <RechartsLegend
              content={<ChartLegendContent hideIcon={false} />}
            />
            <RechartsArea
              type="monotone"
              dataKey="ai"
              stroke="var(--chart-1)"
              strokeWidth={2}
              fill="none"
              activeDot={{ r: 6, strokeWidth: 2, stroke: "var(--chart-1)", fill: "var(--color-background)" }}
            />
            <RechartsArea
              type="monotone"
              dataKey="static"
              stroke="var(--chart-4)"
              strokeWidth={1.5}
              strokeDasharray="4 4"
              fill="none"
              activeDot={{ r: 6, strokeWidth: 2, stroke: "var(--chart-4)", fill: "var(--color-background)" }}
            />
          </RechartsAreaChart>
        </ResponsiveContainer>
      </ChartContainer>
    </div>
  );
}

function RecoveryRateChartSkeleton() {
  return (
    <div className="rounded-xl bg-white/[0.03] p-6">
      <p className="label-sm text-faint">Recovery Rate — AI vs Static (%)</p>
      <PageLoading variant="dashboard" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Recovered by Failure Category — Horizontal Bar Chart              */
/* ------------------------------------------------------------------ */

function CategoryChart({ data }: { data: AnalyticsData['byCategory'] }) {
  if (!data || data.length === 0) {
    return (
      <div className="rounded-xl bg-white/[0.03] p-6">
        <p className="label-sm text-faint">Recovered by Failure Category</p>
        <EmptyState title="No category data yet" copy="Breakdown by failure type (network, insufficient funds, etc.) appears once recoveries settle." />
      </div>
    );
  }

  const chartData = data
    .slice()
    .sort((a, b) => b.recovered - a.recovered)
    .slice(0, 10)
    .map((c) => ({
      label: c.label,
      recovered: c.recovered,
      rate: c.rate,
    }));

  return (
    <div className="rounded-xl bg-white/[0.03] p-6">
      <p className="label-sm text-faint">Recovered by Failure Category</p>
      <ChartContainer
        config={{
          recovered: { label: "Recovered", color: "var(--chart-2)" },
        }}
        className="mt-6 aspect-square"
      >
        <ResponsiveContainer width="100%" height="100%">
          <RechartsBarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 20, right: 20, bottom: 40, left: 100 }}
          >
            <RechartsGrid stroke="rgb(255 255 255 / 0.06)" strokeOpacity={1} vertical={false} />
            <RechartsXAxis
              type="number"
              tickFormatter={(v) => formatLakh(v)}
              tick={{ stroke: "#555b69", fontSize: 11 }}
              tickCount={4}
            />
            <RechartsYAxis
              type="category"
              dataKey="label"
              tick={{ stroke: "#555b69", fontSize: 11 }}
            />
            <RechartsTooltip
              content={<ChartTooltipContent
                indicator="dot"
                // @ts-expect-error - Recharts Formatter type mismatch, but runtime works correctly
                formatter={(value: number, _name: string, _item: any, _index: number, _payload: any[]) => [formatLakh(value), 'Recovered']}
              />}
            />
            <RechartsBar
              dataKey="recovered"
              fill="var(--chart-2)"
              radius={[0, 4, 4, 0]}
              maxBarSize={32}
              onMouseEnter={(e) => e.target.style.opacity = '0.8'}
              onMouseLeave={(e) => e.target.style.opacity = '1'}
            />
          </RechartsBarChart>
        </ResponsiveContainer>
      </ChartContainer>
    </div>
  );
}

function CategoryChartSkeleton() {
  return (
    <div className="rounded-xl bg-white/[0.03] p-6">
      <p className="label-sm text-faint">Recovered by Failure Category</p>
      <PageLoading variant="dashboard" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Recovered by Payment Method — Horizontal Bar Chart                */
/* ------------------------------------------------------------------ */

function MethodChart({ data }: { data: AnalyticsData['byMethod'] }) {
  if (!data || data.length === 0) {
    return (
      <div className="rounded-xl bg-white/[0.03] p-6">
        <p className="label-sm text-faint">Recovered by Payment Method</p>
        <EmptyState title="No method data yet" copy="Recovery rates by payment method (UPI, cards, netbanking) build from your first settled payment." />
      </div>
    );
  }

  const chartData = data.map((m) => ({
    label: m.label,
    recovered: m.recovered,
    rate: m.rate,
    share: m.share,
  }));

  return (
    <div className="rounded-xl bg-white/[0.03] p-6">
      <p className="label-sm text-faint">Recovered by Payment Method</p>
      <ChartContainer
        config={{
          recovered: { label: "Recovered", color: "var(--chart-2)" },
        }}
        className="mt-6 aspect-square"
      >
        <ResponsiveContainer width="100%" height="100%">
          <RechartsBarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 20, right: 20, bottom: 40, left: 100 }}
          >
            <RechartsGrid stroke="rgb(255 255 255 / 0.06)" strokeOpacity={1} vertical={false} />
            <RechartsXAxis
              type="number"
              tickFormatter={(v) => formatLakh(v)}
              tick={{ stroke: "#555b69", fontSize: 11 }}
              tickCount={4}
            />
            <RechartsYAxis
              type="category"
              dataKey="label"
              tick={{ stroke: "#555b69", fontSize: 11 }}
            />
            <RechartsTooltip
              content={<ChartTooltipContent
                indicator="dot"
                // @ts-expect-error - Recharts Formatter type mismatch, but runtime works correctly
                formatter={(value: number, _name: string, _item: any, _index: number, _payload: any[]) => [formatLakh(value), 'Recovered']}
              />}
            />
            <RechartsBar
              dataKey="recovered"
              fill="var(--chart-2)"
              radius={[0, 4, 4, 0]}
              maxBarSize={32}
              onMouseEnter={(e) => e.target.style.opacity = '0.8'}
              onMouseLeave={(e) => e.target.style.opacity = '1'}
            />
          </RechartsBarChart>
        </ResponsiveContainer>
      </ChartContainer>
    </div>
  );
}

function MethodChartSkeleton() {
  return (
    <div className="rounded-xl bg-white/[0.03] p-6">
      <p className="label-sm text-faint">Recovered by Payment Method</p>
      <PageLoading variant="dashboard" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Recovery by Attempt — Simple List                                  */
/* ------------------------------------------------------------------ */

function AttemptChart({ data }: { data: AnalyticsData['byAttempt'] }) {
  if (!data || data.length === 0) {
    return (
      <div className="rounded-xl bg-white/[0.03] p-6">
        <p className="label-sm text-faint">Recovery by Attempt</p>
        <EmptyState title="No attempt data yet" copy="Shows which retry attempt (1st, 2nd, 3rd) recovers the most — builds from multi-attempt recoveries." />
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-white/[0.03] p-6">
      <p className="label-sm text-faint">Recovery by Attempt</p>
      <div className="mt-6 space-y-3 text-[0.8125rem]">
        {data.map((a) => (
          <div key={a.attempt} className="flex items-center justify-between border-b border-border pb-3 last:border-0">
            <span className="text-muted-foreground">Attempt {a.attempt}</span>
            <span className="num text-foreground">
              {formatPct(a.rate, 1)} <span className="ml-3 text-faint">{formatLakh(a.recovered)}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AttemptChartSkeleton() {
  return (
    <div className="rounded-xl bg-white/[0.03] p-6">
      <p className="label-sm text-faint">Recovery by Attempt</p>
      <PageLoading variant="list" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Average Time to Recovery — Comparison Cards                        */
/* ------------------------------------------------------------------ */

function AvgTimeChart({ data }: { data: { static: number; ai: number } }) {
  return (
    <div className="rounded-xl bg-white/[0.03] p-6">
      <p className="label-sm text-faint">Average Time to Recovery</p>
      <div className="mt-6 grid grid-cols-2 gap-6">
        <div className="text-center p-4 rounded-xl bg-white/[0.04] border border-border transition-all duration-200 hover:bg-white/[0.06] hover:border-border/50 hover:shadow-[0_8px_30px_-10px_rgb(0_0_0/0.3)] hover:-translate-y-1">
          <p className="num font-display text-3xl font-bold text-muted-foreground">
            {data.static}h
          </p>
          <p className="label-sm mt-2 text-faint">Static retries</p>
        </div>
        <div className="text-center p-4 rounded-xl bg-success/[0.06] border border-success/[0.12] transition-all duration-200 hover:bg-success/[0.1] hover:border-success/[0.2] hover:shadow-[0_8px_30px_-10px_rgb(34_197_94/0.2)] hover:-translate-y-1">
          <p className="num font-display text-3xl font-bold text-success">
            {data.ai}h
          </p>
          <p className="label-sm mt-2 text-faint">RecoverAI</p>
        </div>
      </div>
    </div>
  );
}

function AvgTimeChartSkeleton() {
  return (
    <div className="rounded-xl bg-white/[0.03] p-6">
      <p className="label-sm text-faint">Average Time to Recovery</p>
      <div className="mt-6 grid grid-cols-2 gap-6">
        <PageLoading variant="content" />
        <PageLoading variant="content" />
      </div>
    </div>
  );
}
