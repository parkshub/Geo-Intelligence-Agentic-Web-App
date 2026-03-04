"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Download,
  MapPin,
  RefreshCcw,
  Send,
  Sparkles,
} from "lucide-react";
import clsx from "clsx";
import dynamic from "next/dynamic";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type {
  AreaProfile,
  ChatMessage,
  CompareAreasPayload,
  DemographicsBenchmark,
  DemographicsProfile,
  ToolCall,
} from "@/lib/types";
import {
  API_BASE,
  bucketToolCalls,
  buildStaticMapUrl,
  downloadTextFile,
  downloadWorksheet,
  formatTimestamp,
  uuid,
} from "@/lib/utils";

const InteractiveAreaMap = dynamic(
  () => import("@/components/InteractiveAreaMap"),
  { ssr: false },
);

const PROMPT_LIBRARY = [
  "Profile 90007. How competitive is Starbucks nearby?",
  "Compare 90007 vs 90210 for high-end coffee campaigns.",
  "What industries should advertise near USC within 3km?",
];

const INITIAL_ASSISTANT: ChatMessage = {
  id: uuid(),
  role: "assistant",
  content:
    "I am your geo-intelligence agent. Ask me about zip codes, brands, campaign ideas, or compare two markets.",
  timestamp: formatTimestamp(),
  localOnly: true,
};

type WorksheetContext = {
  lastMessage?: ChatMessage;
  profiles: AreaProfile[];
  comparison?: CompareAreasPayload;
};

export default function Home() {
  const [messages, setMessages] = useState<ChatMessage[]>([INITIAL_ASSISTANT]);
  const [isHydrated, setIsHydrated] = useState(false);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [profiles, setProfiles] = useState<AreaProfile[]>([]);
  const [comparison, setComparison] = useState<unknown>(null);
  const [demographicsProfiles, setDemographicsProfiles] = useState<DemographicsProfile[]>([]);
  const [demographicsNational, setDemographicsNational] =
    useState<DemographicsBenchmark | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const latestAssistant = messages.filter((m) => m.role === "assistant").at(-1);

  useEffect(() => {
    setIsHydrated(true);
  }, []);

  const handleSend = async (prompt?: string) => {
    const content = (prompt ?? input).trim();
    if (!content) return;
    const newMessage: ChatMessage = {
      id: uuid(),
      role: "user",
      content,
      timestamp: formatTimestamp(),
    };
    const nextMessages = [...messages, newMessage];
    setMessages(nextMessages);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: nextMessages
            .filter((msg) => !msg.localOnly)
            .map((msg) => ({
              role: msg.role,
              content: msg.content,
            })),
        }),
      });

      if (!response.ok) {
        throw new Error(`Agent error (${response.status})`);
      }

      const data = await response.json();
      const assistantMessage: ChatMessage = {
        id: uuid(),
        role: "assistant",
        content: data.output ?? "No response returned.",
        timestamp: formatTimestamp(),
      };
      const nextToolCalls = (data.tool_calls ?? []) as ToolCall[];
      const buckets = bucketToolCalls(nextToolCalls);

      const dedupeProfiles = (items: AreaProfile[]) => {
        const seen = new Set<string>();
        return items.filter((item) => {
          const key = item.query;
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
      };

      const dedupeDemographics = (items: DemographicsProfile[]) => {
        const seen = new Set<string>();
        return items.filter((item) => {
          const key = item.zip_code || item.label;
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
      };

      setMessages((prev) => [...prev, assistantMessage]);
      setToolCalls((prev) => [...prev, ...nextToolCalls]);

      if (buckets.profiles.length > 0) {
        const nextProfiles = dedupeProfiles(buckets.profiles).slice(0, 2);
        setProfiles(nextProfiles);
        setComparison(buckets.comparison ?? null);
      } else if (buckets.comparison) {
        setComparison(buckets.comparison);
      }

      if (buckets.demographicsProfiles.length > 0) {
        const nextDemographics = dedupeDemographics(buckets.demographicsProfiles).slice(0, 2);
        setDemographicsProfiles(nextDemographics);
        setDemographicsNational(buckets.demographicsNational ?? null);
      } else if (buckets.demographicsNational) {
        setDemographicsNational(buckets.demographicsNational);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const handleWorksheet = () => {
    const context: WorksheetContext = {
      lastMessage: latestAssistant,
      profiles,
      comparison: comparison as CompareAreasPayload | undefined,
    };
    const markdown = buildWorksheet(context);
    downloadWorksheet(markdown, `geo-intel-${Date.now()}.md`);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto grid max-w-6xl gap-6 px-6 py-10 lg:grid-cols-[2fr,1fr]">
        <section className="rounded-3xl border border-white/10 bg-slate-900/70 p-6 shadow-2xl shadow-blue-900/30">
          <header className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm uppercase tracking-wide text-blue-300">
                Geo-Intel Studio
              </p>
              <h1 className="text-2xl font-semibold">
                Location Intelligence Agent
              </h1>
            </div>
            <button
              onClick={handleWorksheet}
              disabled={!latestAssistant}
              className="inline-flex items-center gap-2 rounded-full border border-white/20 px-4 py-2 text-sm text-blue-100 transition hover:border-white/40 disabled:opacity-40"
            >
              <Download size={16} />
              Export Worksheet
            </button>
          </header>

          <div className="mb-4 grid gap-2 sm:grid-cols-3">
            {PROMPT_LIBRARY.map((prompt) => (
              <button
                key={prompt}
                onClick={() => handleSend(prompt)}
                className="rounded-2xl border border-white/15 bg-white/5 px-3 py-3 text-left text-sm transition hover:bg-white/10"
              >
                {prompt}
              </button>
            ))}
          </div>

          <div className="space-y-3 rounded-3xl bg-slate-950/40 p-4">
            {messages.map((message) => (
              <article
                key={message.id}
                className={clsx(
                  "rounded-2xl border px-4 py-3 text-sm shadow-sm",
                  message.role === "user"
                    ? "border-blue-500/30 bg-blue-500/10 text-blue-100"
                    : "border-slate-800 bg-slate-900/80 text-slate-100",
                )}
              >
                <div className="flex items-center justify-between text-xs uppercase tracking-wide text-slate-400">
                  <span>{message.role === "user" ? "You" : "Agent"}</span>
                  <span suppressHydrationWarning>
                    {isHydrated ? message.timestamp : ""}
                  </span>
                </div>
                {message.role === "assistant" ? (
                  <div className="mt-2 text-base leading-relaxed">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        h1: ({ children }) => (
                          <h1 className="mb-2 mt-3 text-xl font-semibold">{children}</h1>
                        ),
                        h2: ({ children }) => (
                          <h2 className="mb-2 mt-3 text-lg font-semibold">{children}</h2>
                        ),
                        h3: ({ children }) => (
                          <h3 className="mb-1 mt-2 text-base font-semibold">{children}</h3>
                        ),
                        p: ({ children }) => <p className="mb-2">{children}</p>,
                        ul: ({ children }) => (
                          <ul className="mb-2 list-disc space-y-1 pl-5">{children}</ul>
                        ),
                        ol: ({ children }) => (
                          <ol className="mb-2 list-decimal space-y-1 pl-5">{children}</ol>
                        ),
                        strong: ({ children }) => (
                          <strong className="font-semibold text-white">{children}</strong>
                        ),
                        a: ({ href, children }) => (
                          <a
                            href={href}
                            target="_blank"
                            rel="noreferrer"
                            className="text-blue-300 underline hover:text-blue-200"
                          >
                            {children}
                          </a>
                        ),
                      }}
                    >
                      {message.content}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <p className="mt-2 whitespace-pre-line text-base leading-relaxed">
                    {message.content}
                  </p>
                )}
              </article>
            ))}
            {error && (
              <p className="rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
                {error}
              </p>
            )}
          </div>

          <footer className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end">
            <button
              onClick={() => {
                setToolCalls([]);
                setProfiles([]);
                setComparison(null);
                setDemographicsProfiles([]);
                setDemographicsNational(null);
              }}
              className="inline-flex items-center gap-2 rounded-full border border-white/15 px-4 py-2 text-xs text-slate-200 transition hover:border-white/40"
            >
              <RefreshCcw size={14} />
              Reset Tool Console
            </button>
          </footer>

          <div className="mt-4 flex gap-2 rounded-2xl border border-white/10 bg-slate-900/50 p-2">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Ask about a ZIP, brand, or campaign goal..."
              className="flex-1 rounded-2xl border border-transparent bg-transparent px-3 text-sm text-white placeholder:text-slate-500 focus:border-blue-400 focus:outline-none"
            />
            <button
              onClick={() => handleSend()}
              disabled={loading}
              className="inline-flex items-center justify-center rounded-2xl bg-blue-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-500/40 transition hover:bg-blue-400 disabled:opacity-50"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <Sparkles size={16} className="animate-pulse" /> Thinking
                </span>
              ) : (
                <>
                  <Send size={16} className="mr-2" />
                  Send
                </>
              )}
            </button>
          </div>
        </section>

        <aside className="flex flex-col gap-6">
          <ToolConsole toolCalls={toolCalls} />
          <InsightsPanel
            profiles={profiles}
            comparison={comparison}
            demographicsProfiles={demographicsProfiles}
            demographicsNational={demographicsNational}
          />
        </aside>
      </div>
    </div>
  );
}

function ToolConsole({ toolCalls }: { toolCalls: ToolCall[] }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-slate-900/60 p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-semibold uppercase tracking-wide text-blue-200">
          Tool Call Console
        </p>
        <span className="text-xs text-slate-400">
          {toolCalls.length} calls
        </span>
      </div>
      <div className="space-y-2 max-h-[320px] overflow-y-auto pr-1">
        {toolCalls.length === 0 && (
          <p className="text-sm text-slate-400">
            Tools will appear here once the agent starts reasoning.
          </p>
        )}
        {toolCalls.map((call, index) => (
          <article
            key={`${call.tool}-${index}`}
            className="rounded-2xl border border-white/10 bg-slate-950/40 p-3 text-xs"
          >
            <div className="flex items-center justify-between text-slate-300">
              <div className="inline-flex items-center gap-2">
                <span className="rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-blue-200">
                  {call.tool}
                </span>
                <span className="text-slate-500">
                  params: {Object.keys(call.input ?? {}).length}
                </span>
              </div>
              <Activity size={14} className="text-slate-500" />
            </div>
            <pre className="mt-2 truncate whitespace-pre-wrap text-slate-200">
              {JSON.stringify(call.input, null, 2)}
            </pre>
          </article>
        ))}
      </div>
    </div>
  );
}

function InsightsPanel({
  profiles,
  comparison,
  demographicsProfiles,
  demographicsNational,
}: {
  profiles: AreaProfile[];
  comparison: unknown;
  demographicsProfiles: DemographicsProfile[];
  demographicsNational: DemographicsBenchmark | null;
}) {
  const typedComparison = comparison as CompareAreasPayload | undefined;
  return (
    <div className="rounded-3xl border border-white/10 bg-slate-900/60 p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold uppercase tracking-wide text-blue-200">
          Insights
        </p>
        <MapPin size={16} className="text-slate-400" />
      </div>

      <div className="mt-4 space-y-4">
        {profiles.slice(0, 2).map((profile) => (
          <AreaCard key={profile.query} profile={profile} />
        ))}

        {typedComparison && (
          <div className="rounded-2xl border border-amber-400/30 bg-amber-500/10 p-4 text-sm text-amber-100">
            <p className="text-xs uppercase tracking-wide">Comparison Result</p>
            <p className="text-lg font-semibold text-amber-200">
              Winner: {typedComparison.winner}
            </p>
            <p className="mt-1 text-amber-100">{typedComparison.rationale}</p>
          </div>
        )}

        {demographicsProfiles.length > 0 && (
          <DemographicsPanel
            profiles={demographicsProfiles}
            nationalAverage={demographicsNational}
          />
        )}
      </div>
    </div>
  );
}

function DemographicsPanel({
  profiles,
  nationalAverage,
}: {
  profiles: DemographicsProfile[];
  nationalAverage: DemographicsBenchmark | null;
}) {
  const seen = new Set<string>();
  const selectedProfiles = profiles
    .filter((profile) => {
      const key = profile.zip_code || profile.label;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 2);

  const demographicRows = [
    ...selectedProfiles.map((profile) => ({
      label: profile.zip_code || profile.label,
      income: profile.median_household_income ?? 0,
      age: profile.median_age ?? 0,
      poverty: profile.poverty_rate_pct ?? 0,
      education: profile.education_bachelor_plus_pct ?? 0,
      race_white_pct: profile.race_white_pct ?? 0,
      race_black_pct: profile.race_black_pct ?? 0,
      race_asian_pct: profile.race_asian_pct ?? 0,
      hispanic_pct: profile.hispanic_pct ?? 0,
    })),
    {
      label: "US AVG",
      income: nationalAverage?.median_household_income ?? 0,
      age: nationalAverage?.median_age ?? 0,
      poverty: nationalAverage?.poverty_rate_pct ?? 0,
      education: nationalAverage?.education_bachelor_plus_pct ?? 0,
      race_white_pct: nationalAverage?.race_white_pct ?? 0,
      race_black_pct: nationalAverage?.race_black_pct ?? 0,
      race_asian_pct: nationalAverage?.race_asian_pct ?? 0,
      hispanic_pct: nationalAverage?.hispanic_pct ?? 0,
    },
  ];

  const metricCards = [
    {
      key: "income",
      label: "Median Household Income",
      accessor: (row: (typeof demographicRows)[number]) => row.income,
      formatter: (value: number) => `$${Math.round(value).toLocaleString()}`,
      color: "#3b82f6",
    },
    {
      key: "age",
      label: "Median Age",
      accessor: (row: (typeof demographicRows)[number]) => row.age,
      formatter: (value: number) => value.toFixed(1),
      color: "#a855f7",
    },
    {
      key: "poverty",
      label: "Poverty Rate",
      accessor: (row: (typeof demographicRows)[number]) => row.poverty,
      formatter: (value: number) => `${value.toFixed(1)}%`,
      color: "#ef4444",
    },
    {
      key: "education",
      label: "Bachelor+ Education",
      accessor: (row: (typeof demographicRows)[number]) => row.education,
      formatter: (value: number) => `${value.toFixed(1)}%`,
      color: "#10b981",
    },
  ] as const;

  const raceSegments = [
    { key: "race_white_pct", label: "White", color: "#60a5fa" },
    { key: "race_black_pct", label: "Black", color: "#f59e0b" },
    { key: "race_asian_pct", label: "Asian", color: "#34d399" },
    { key: "hispanic_pct", label: "Hispanic", color: "#f472b6" },
  ] as const;

  const getRaceGradient = (row: (typeof demographicRows)[number]) => {
    let current = 0;
    const parts = raceSegments.map((segment) => {
      const value = Math.max(0, row[segment.key] ?? 0);
      const start = current;
      current += value;
      return `${segment.color} ${start}% ${Math.min(current, 100)}%`;
    });
    if (current <= 0) return "conic-gradient(#334155 0% 100%)";
    return `conic-gradient(${parts.join(", ")})`;
  };

  const toSafeText = (value: string) =>
    value
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&apos;");

  const pieSlicePath = (
    cx: number,
    cy: number,
    r: number,
    startDeg: number,
    endDeg: number,
  ) => {
    const startRad = (Math.PI / 180) * startDeg;
    const endRad = (Math.PI / 180) * endDeg;
    const x1 = cx + r * Math.cos(startRad);
    const y1 = cy + r * Math.sin(startRad);
    const x2 = cx + r * Math.cos(endRad);
    const y2 = cy + r * Math.sin(endRad);
    const largeArc = endDeg - startDeg > 180 ? 1 : 0;
    return `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`;
  };

  const handleDownloadGraph = () => {
    if (demographicRows.length === 0) return;
    const width = 1400;
    const metricHeight = 170;
    const raceRowsCount = Math.ceil(demographicRows.length / 2);
    const height = 140 + metricHeight * metricCards.length + raceRowsCount * 280 + 70;

    const metricSvgs = metricCards
      .map((metric, metricIndex) => {
        const maxValue = Math.max(...demographicRows.map((row) => metric.accessor(row)), 1);
        const cardX = 40;
        const cardY = 90 + metricIndex * metricHeight;
        const cardW = width - 80;
        const cardH = 145;
        const barAreaW = cardW - 220;
        const rowGap = 24;
        const barTop = cardY + 38;
        const barH = 12;
        const bars = demographicRows
          .map((row, rowIndex) => {
            const value = metric.accessor(row);
            const normalized = Math.max(0, Math.min(1, value / maxValue));
            const x = cardX + 180;
            const y = barTop + rowIndex * rowGap;
            const w = Math.max(2, normalized * barAreaW);
            return `<text x="${cardX + 14}" y="${y + 10}" fill="#e2e8f0" font-size="12">${toSafeText(row.label)}</text>
<rect x="${x}" y="${y}" width="${barAreaW}" height="${barH}" fill="#1e293b" rx="6"/>
<rect x="${x}" y="${y}" width="${w}" height="${barH}" fill="${metric.color}" rx="6"/>
<text x="${x + barAreaW + 10}" y="${y + 10}" fill="#cbd5e1" font-size="12">${metric.formatter(value)}</text>`;
          })
          .join("\n");
        return `<rect x="${cardX}" y="${cardY}" width="${cardW}" height="${cardH}" rx="12" fill="#0b1220" stroke="#334155"/>
<text x="${cardX + 14}" y="${cardY + 22}" fill="#e2e8f0" font-size="14">${metric.label}</text>
${bars}`;
      })
      .join("\n");

    const raceSectionY = 90 + metricCards.length * metricHeight + 14;
    const pieCards = demographicRows
      .map((row, index) => {
        const col = index % 2;
        const rowIndex = Math.floor(index / 2);
        const cardW = 640;
        const cardH = 250;
        const cardX = 40 + col * (cardW + 40);
        const cardY = raceSectionY + rowIndex * 280;
        const cx = cardX + 160;
        const cy = cardY + 130;
        const radius = 70;

        let currentDeg = -90;
        const total = raceSegments.reduce(
          (sum, segment) => sum + Math.max(0, row[segment.key] ?? 0),
          0,
        );
        const slices = total > 0
          ? raceSegments
              .map((segment) => {
                const value = Math.max(0, row[segment.key] ?? 0);
                const span = (value / total) * 360;
                const start = currentDeg;
                const end = currentDeg + span;
                currentDeg = end;
                if (span <= 0) return "";
                return `<path d="${pieSlicePath(cx, cy, radius, start, end)}" fill="${segment.color}" />`;
              })
              .join("\n")
          : `<circle cx="${cx}" cy="${cy}" r="${radius}" fill="#334155" />`;

        const legend = raceSegments
          .map((segment, legendIdx) => {
            const value = Math.max(0, row[segment.key] ?? 0);
            const lx = cardX + 300;
            const ly = cardY + 78 + legendIdx * 34;
            return `<rect x="${lx}" y="${ly - 10}" width="12" height="12" fill="${segment.color}" rx="2"/>
<text x="${lx + 20}" y="${ly}" fill="#cbd5e1" font-size="12">${segment.label}: ${value.toFixed(1)}%</text>`;
          })
          .join("\n");

        return `<rect x="${cardX}" y="${cardY}" width="${cardW}" height="${cardH}" rx="12" fill="#0b1220" stroke="#334155"/>
<text x="${cardX + 14}" y="${cardY + 24}" fill="#e2e8f0" font-size="14">Race Composition - ${toSafeText(row.label)}</text>
${slices}
${legend}`;
      })
      .join("\n");

    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
<defs>
  <style>
    text {
      font-family: Inter, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    .dashboard-title {
      font-size: 24px;
      font-weight: 600;
      fill: #e2e8f0;
    }
    .dashboard-subtitle {
      font-size: 13px;
      fill: #94a3b8;
    }
  </style>
</defs>
<rect width="100%" height="100%" fill="#020617" />
<text x="40" y="42" class="dashboard-title">Demographics Dashboard</text>
<text x="40" y="65" class="dashboard-subtitle">Up to 2 ZIP codes + National Average</text>
${metricSvgs}
${pieCards}
</svg>`;

    downloadTextFile(svg, `demographics-dashboard-${Date.now()}.svg`, "image/svg+xml");
  };

  return (
    <div className="rounded-2xl border border-cyan-400/25 bg-cyan-500/5 p-4 text-sm">
      <div className="flex items-center justify-between">
        <p className="text-xs uppercase tracking-wide text-cyan-200">
          Demographics Graphs
        </p>
        <button
          onClick={handleDownloadGraph}
          className="rounded-full border border-cyan-300/30 px-3 py-1 text-[11px] text-cyan-100 hover:border-cyan-200/50"
        >
          Download Dashboard SVG
        </button>
      </div>

      <p className="mt-2 text-[11px] text-slate-400">
        Showing up to 2 ZIP codes plus national average.
      </p>

      <div className="mt-3 grid gap-3">
        {metricCards.map((metric) => {
          const maxValue = Math.max(...demographicRows.map((row) => metric.accessor(row)), 1);
          return (
            <div
              key={metric.key}
              className="rounded-xl border border-white/10 bg-slate-950/40 p-3"
            >
              <p className="text-[11px] uppercase tracking-wide text-slate-400">
                {metric.label}
              </p>
              <div className="mt-2 space-y-2">
                {demographicRows.map((row) => {
                  const value = metric.accessor(row);
                  return (
                    <div key={`${metric.key}-${row.label}`}>
                      <div className="mb-1 flex justify-between text-xs text-slate-300">
                        <span>{row.label}</span>
                        <span>{metric.formatter(value)}</span>
                      </div>
                      <div className="h-2 rounded-full bg-slate-800">
                        <div
                          className="h-2 rounded-full"
                          style={{
                            width: `${(Math.max(value, 0) / maxValue) * 100}%`,
                            backgroundColor: metric.color,
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-3 rounded-xl border border-white/10 bg-slate-950/40 p-3">
        <p className="text-[11px] uppercase tracking-wide text-slate-400">
          Race Composition
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {demographicRows.map((row) => (
            <div
              key={`race-${row.label}`}
              className="rounded-lg border border-white/10 bg-slate-900/60 p-3"
            >
              <p className="text-xs font-semibold text-slate-200">{row.label}</p>
              <div className="mt-2 flex items-center gap-4">
                <div
                  className="h-24 w-24 rounded-full border border-white/20"
                  style={{ background: getRaceGradient(row) }}
                />
                <div className="space-y-1 text-xs text-slate-300">
                  {raceSegments.map((segment) => (
                    <p key={`${row.label}-${segment.label}`}>
                      {segment.label}: {Math.max(0, row[segment.key] ?? 0).toFixed(1)}%
                    </p>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function AreaCard({ profile }: { profile: AreaProfile }) {
  const mapUrl =
    profile.centroid && buildStaticMapUrl(profile.centroid, profile.query);
  const competitorPoints = profile.top_competitors.filter(
    (competitor) =>
      typeof competitor.lat === "number" && typeof competitor.lon === "number",
  );

  return (
    <article className="rounded-2xl border border-white/10 bg-slate-950/40 p-4 text-sm">
      <div className="flex items-center justify-between text-xs uppercase tracking-wide text-slate-400">
        <span>{profile.query}</span>
        <span>Saturation {profile.saturation_score.toFixed(0)}</span>
      </div>
      <p className="mt-2 text-2xl font-semibold text-white">
        Demand proxy {profile.demand_proxy_score.toFixed(1)}
      </p>
      {profile.centroid ? (
        <div className="mt-3 h-40 w-full overflow-hidden rounded-xl border border-white/10">
          <InteractiveAreaMap
            centroid={profile.centroid}
            query={profile.query}
            competitors={competitorPoints.map((competitor) => ({
              name: competitor.name,
              lat: competitor.lat!,
              lon: competitor.lon!,
            }))}
          />
        </div>
      ) : mapUrl ? (
        <img
          src={mapUrl}
          alt={`Map of ${profile.query}`}
          className="mt-3 h-36 w-full rounded-xl object-cover"
        />
      ) : null}
      <div className="mt-3 space-y-1 text-xs text-slate-300">
        {profile.notes?.map((note) => (
          <p key={note}>• {note}</p>
        )) ?? <p>• No custom notes returned.</p>}
      </div>
      <div className="mt-3 rounded-xl border border-white/10 bg-white/5 p-2 text-xs text-slate-200">
        <p className="text-[11px] uppercase tracking-wide text-slate-400">
          Top Competitors
        </p>
        <ul className="mt-2 space-y-1">
          {profile.top_competitors?.slice(0, 5).length
            ? profile.top_competitors
                ?.slice(0, 5)
                .map((competitor) => (
                  <li
                    key={competitor.name}
                    className="flex items-center justify-between"
                  >
                    <span>{competitor.name}</span>
                    {(competitor.rank_popularity ?? 0) > 0 ? (
                      <span className="text-slate-500">
                        {competitor.rank_popularity?.toFixed(1)}
                      </span>
                    ) : null}
                  </li>
                ))
            : (
              <li>No competitors returned.</li>
            )}
        </ul>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        Demand scores are proxy metrics derived from density, brand presence,
        and ranking signals—this is not measured foot traffic.
      </p>
    </article>
  );
}

function buildWorksheet({ lastMessage, profiles, comparison }: WorksheetContext) {
  const lines = [
    `# Geo-Intel Scenario (${new Date().toLocaleDateString()})`,
    "",
    lastMessage ? `**Agent Summary**: ${lastMessage.content}` : "",
    "",
  ];
  profiles.forEach((profile) => {
    lines.push(`## ${profile.query}`);
    lines.push(
      `- Demand Proxy: ${profile.demand_proxy_score.toFixed(1)} (proxy)`,
    );
    lines.push(`- Saturation: ${profile.saturation_score.toFixed(1)}`);
    lines.push(
      "- Notes: " + (profile.notes?.join("; ") ?? "No qualitative notes."),
    );
    lines.push("");
  });
  if (comparison) {
    lines.push("## Comparison Outcome");
    lines.push(`Winner: ${(comparison as CompareAreasPayload).winner}`);
    lines.push(
      `Rationale: ${(comparison as CompareAreasPayload).rationale ?? "N/A"}`,
    );
  }
  return lines.filter(Boolean).join("\n");
}
