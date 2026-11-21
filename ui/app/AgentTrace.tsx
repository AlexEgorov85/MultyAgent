"use client";

import { useAuiState } from "@assistant-ui/react";
import { useI18n } from "./i18n";

type TraceStep = {
  step: string;
  title: string;
  detail?: string;
  status?: string;
};

export function AgentTrace() {
  const { t } = useI18n();
  const custom = useAuiState((state) => state.message.metadata?.custom);
  const trace =
    ((custom as { trace?: TraceStep[] } | undefined)?.trace ?? []).filter(
      (step) => step && step.title,
    );

  if (trace.length === 0) return null;

  return (
    <details className="mt-3 border-t app-border pt-2">
      <summary className="cursor-pointer select-none text-xs font-medium app-muted transition app-accent-hover">
        {t.agentPath} · {trace.length}
      </summary>
      <ol className="mt-2 space-y-2">
        {trace.map((step, index) => (
          <li key={`${step.step}-${index}`} className="flex gap-2 text-xs">
            <span
              className={
                step.status === "warn"
                  ? "mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500"
                  : "mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500"
              }
            />
            <div className="min-w-0">
              <div className="font-medium app-text">{step.title}</div>
              {step.detail ? (
                <div className="mt-0.5 whitespace-pre-wrap break-words font-mono text-[0.7rem] leading-relaxed app-muted">
                  {step.detail}
                </div>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </details>
  );
}
