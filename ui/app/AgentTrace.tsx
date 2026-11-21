"use client";

import { useAuiState } from "@assistant-ui/react";
import { type ReactNode } from "react";
import { type TraceStep, type TraceChip } from "./chats";
import { useI18n } from "./i18n";

const STEP_ICONS: Record<string, ReactNode> = {
  message: (
    <path d="M21 11.5a8.4 8.4 0 0 1-8.5 8.5 9 9 0 0 1-3.8-.8L3 21l1.8-5.2A8.4 8.4 0 0 1 12.5 3 8.4 8.4 0 0 1 21 11.5Z" />
  ),
  route: (
    <>
      <circle cx="6" cy="5" r="2" />
      <circle cx="18" cy="19" r="2" />
      <path d="M6 7v3a4 4 0 0 0 4 4h4a4 4 0 0 1 4 4v1" />
    </>
  ),
  memory: (
    <>
      <circle cx="12" cy="8" r="3.2" />
      <path d="M5.5 20a6.5 6.5 0 0 1 13 0" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3.5 19 6v5.2c0 4.2-2.8 7.1-7 8.8-4.2-1.7-7-4.6-7-8.8V6Z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  database: (
    <>
      <ellipse cx="12" cy="6" rx="7" ry="3" />
      <path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6" />
      <path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3" />
    </>
  ),
  table: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M4 9h16M9 9v11" />
    </>
  ),
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="6" />
      <path d="m15 15 5 5" />
    </>
  ),
  book: (
    <>
      <path d="M4 5a2 2 0 0 1 2-2h13v18H6a2 2 0 0 1-2-2Z" />
      <path d="M8 3v18" />
    </>
  ),
  file: (
    <>
      <path d="M6 3h8l4 4v14H6Z" />
      <path d="M14 3v4h4M9 12h6M9 16h6" />
    </>
  ),
  check: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="m8.5 12 2.5 2.5 4.5-5" />
    </>
  ),
  compass: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="m14.5 9.5-1.5 4-4 1.5 1.5-4Z" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v4l3 2" />
    </>
  ),
  default: <circle cx="12" cy="12" r="3" />,
};

type Tone = "ok" | "warn" | "error";

function toneOf(status?: string): Tone {
  const value = (status ?? "").toLowerCase();
  if (value === "warn" || value === "warning") return "warn";
  if (value === "error" || value === "failed" || value === "danger") {
    return "error";
  }
  return "ok";
}

function StepIcon({ kind }: { kind?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-3 w-3"
      aria-hidden="true"
    >
      {STEP_ICONS[kind ?? "default"] ?? STEP_ICONS.default}
    </svg>
  );
}

function TraceGlyph() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-3.5 w-3.5"
      aria-hidden="true"
    >
      <circle cx="5" cy="6" r="1.7" />
      <circle cx="19" cy="18" r="1.7" />
      <path d="M6.7 6H15a4 4 0 0 1 0 8H9a4 4 0 0 0 0 8h8.3" />
    </svg>
  );
}

function StepChips({ chips }: { chips: TraceChip[] }) {
  if (chips.length === 0) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {chips.map((chip, index) => (
        <span
          key={`${chip.label}-${index}`}
          className="app-trace-chip inline-flex items-center gap-1 px-1.5 py-0.5 text-[0.65rem] leading-none"
        >
          <span className="app-muted-2">{chip.label}</span>
          <span className="font-medium app-text">{chip.value}</span>
        </span>
      ))}
    </div>
  );
}

export function AgentTrace() {
  const { t } = useI18n();
  const custom = useAuiState((state) => state.message.metadata?.custom);
  const trace = (
    (custom as { trace?: TraceStep[] } | undefined)?.trace ?? []
  ).filter((step) => step && step.title);

  if (trace.length === 0) return null;

  const visible = trace.filter((step) => step.step !== "latency");
  if (visible.length === 0) return null;

  const routeStep =
    trace.find((step) => step.route_label) ??
    trace.find((step) => step.step === "route");
  const routeLabel = routeStep?.route_label;
  const duration = trace.find(
    (step) => typeof step.duration_s === "number",
  )?.duration_s;
  const warnings = visible.filter((step) => toneOf(step.status) !== "ok").length;
  const durationLabel =
    typeof duration === "number"
      ? t.agentPathSeconds.replace("{seconds}", duration.toFixed(1))
      : undefined;
  const warningsLabel = t.agentPathWarnings.replace(
    "{count}",
    String(warnings),
  );

  return (
    <details className="app-trace mt-3 border-t app-border pt-2">
      <summary className="app-trace-summary flex cursor-pointer items-center gap-2 py-1 text-xs">
        <span className="app-trace-badge flex h-5 w-5 shrink-0 items-center justify-center rounded-full">
          <TraceGlyph />
        </span>
        <span className="shrink-0 font-medium app-text">{t.agentPath}</span>
        {routeLabel ? (
          <span className="app-trace-chip min-w-0 truncate px-1.5 py-0.5 text-[0.65rem] leading-none">
            {routeLabel}
          </span>
        ) : null}
        <span className="ml-auto flex shrink-0 items-center gap-1.5 text-[0.68rem] app-muted-2">
          {warnings > 0 ? (
            <span className="app-trace-warn px-1 py-0.5" title={warningsLabel}>
              {warnings}
            </span>
          ) : null}
          {durationLabel ? (
            <span className="tabular-nums">{durationLabel}</span>
          ) : null}
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="app-trace-chevron h-3 w-3"
            aria-hidden="true"
          >
            <path d="m9 18 6-6-6-6" />
          </svg>
        </span>
      </summary>

      <ol className="relative mt-2">
        <span
          aria-hidden="true"
          className="app-trace-line absolute bottom-2 left-[11px] top-2 w-px"
        />
        {visible.map((step, index) => {
          const tone = toneOf(step.status);
          const showAgent =
            index === 0 || visible[index - 1]?.agent !== step.agent;
          // Если у шага есть компактные метрики, не дублируем их текстом.
          // Для маршрута и ACL текст важен и без метрик.
          const keepDetail =
            step.step === "route" ||
            step.step === "acl" ||
            step.step === "followup" ||
            !step.chips?.length;
          const detail =
            keepDetail && step.detail && step.detail !== step.code
              ? step.detail
              : undefined;
          return (
            <li
              key={`${step.step}-${index}`}
              className="relative flex gap-2.5 pb-2.5 last:pb-0"
            >
              <span
                className="app-trace-dot relative z-10 mt-0.5 flex h-[23px] w-[23px] shrink-0 items-center justify-center rounded-full"
                data-status={tone}
                title={tone === "ok" ? undefined : warningsLabel}
              >
                <StepIcon kind={step.kind} />
              </span>
              <div className="min-w-0 flex-1 pt-0.5">
                {showAgent && step.agent ? (
                  <div className="mb-0.5 text-[0.6rem] font-semibold uppercase tracking-[0.08em] app-muted-2">
                    {step.agent}
                  </div>
                ) : null}
                <div className="text-xs font-medium leading-snug app-text">
                  {step.title}
                </div>
                {detail ? (
                  <div className="mt-0.5 whitespace-pre-wrap break-words text-[0.72rem] leading-relaxed app-muted">
                    {detail}
                  </div>
                ) : null}
                {step.chips ? <StepChips chips={step.chips} /> : null}
                {step.code ? (
                  <details className="group mt-1.5">
                    <summary className="app-trace-code-toggle cursor-pointer select-none text-[0.68rem] font-medium app-accent-text">
                      <span className="group-open:hidden">{t.agentPathShowSql}</span>
                      <span className="hidden group-open:inline">
                        {t.agentPathHideSql}
                      </span>
                    </summary>
                    <pre className="app-trace-code aui-scrollbar mt-1 max-h-56 overflow-auto p-2 text-[0.68rem] leading-relaxed">
                      <code>{step.code}</code>
                    </pre>
                  </details>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </details>
  );
}
