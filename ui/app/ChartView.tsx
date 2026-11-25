"use client";

import { useI18n } from "./i18n";
import { type ChartPoint, type ChartSpec } from "./chart";

const PALETTE = [
  "#6366f1",
  "#8b5cf6",
  "#0ea5e9",
  "#10b981",
  "#f59e0b",
  "#f43f5e",
  "#14b8a6",
  "#a855f7",
];

function useNumberFormatter() {
  const { lang } = useI18n();
  return new Intl.NumberFormat(lang === "en" ? "en-US" : "ru-RU", {
    maximumFractionDigits: 1,
  });
}

function BarChart({ data }: { data: ChartPoint[] }) {
  const format = useNumberFormatter();
  const max = Math.max(...data.map((point) => point.value), 1);

  return (
    <div className="app-chart-bars" role="img" aria-label="Bar chart">
      {data.map((point, index) => (
        <div className="app-chart-bar-row" key={`${point.label}-${index}`}>
          <div className="app-chart-bar-label" title={point.label}>
            {point.label}
          </div>
          <div className="app-chart-bar-track">
            <div
              className="app-chart-bar-fill"
              style={{ width: `${Math.max(2, (point.value / max) * 100)}%` }}
            />
          </div>
          <div className="app-chart-bar-value">{format.format(point.value)}</div>
        </div>
      ))}
    </div>
  );
}

function LineChart({ data }: { data: ChartPoint[] }) {
  const format = useNumberFormatter();
  const width = 640;
  const height = 260;
  const padding = { left: 48, right: 16, top: 18, bottom: 52 };
  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;

  const labels: string[] = [];
  for (const point of data) {
    if (!labels.includes(point.label)) labels.push(point.label);
  }
  const groups = new Map<string, ChartPoint[]>();
  for (const point of data) {
    const key = point.series ?? "";
    const list = groups.get(key) ?? [];
    list.push(point);
    groups.set(key, list);
  }
  const series = Array.from(groups.entries());
  const multiple = series.length > 1;
  const max = Math.max(...data.map((point) => point.value), 1);
  const step = labels.length > 1 ? innerW / (labels.length - 1) : 0;
  const xFor = (label: string) =>
    padding.left +
    (labels.length > 1 ? labels.indexOf(label) * step : innerW / 2);
  const yFor = (value: number) =>
    padding.top + innerH - (value / max) * innerH;
  const labelEvery = Math.max(1, Math.ceil(labels.length / 6));

  return (
    <div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="app-chart-svg"
        role="img"
        aria-label="Line chart"
      >
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = padding.top + innerH * ratio;
          return (
            <g key={ratio}>
              <line
                x1={padding.left}
                x2={width - padding.right}
                y1={y}
                y2={y}
                className="app-chart-grid"
              />
              <text
                x={padding.left - 8}
                y={y + 3}
                textAnchor="end"
                className="app-chart-axis"
              >
                {format.format(max * (1 - ratio))}
              </text>
            </g>
          );
        })}
        {series.map(([name, points], index) => {
          const color = PALETTE[index % PALETTE.length];
          const sorted = [...points].sort(
            (a, b) => labels.indexOf(a.label) - labels.indexOf(b.label),
          );
          const path = sorted
            .map(
              (point, pointIndex) =>
                `${pointIndex === 0 ? "M" : "L"}${xFor(point.label)},${yFor(
                  point.value,
                )}`,
            )
            .join(" ");
          return (
            <g key={`${name}-${index}`}>
              <path
                d={path}
                className="app-chart-line"
                style={multiple ? { stroke: color } : undefined}
              />
              {sorted.map((point, pointIndex) => (
                <circle
                  key={`${point.label}-${pointIndex}`}
                  cx={xFor(point.label)}
                  cy={yFor(point.value)}
                  r="4"
                  className="app-chart-point"
                  style={multiple ? { fill: color } : undefined}
                >
                  <title>
                    {name ? `${name} · ` : ""}
                    {point.label}: {format.format(point.value)}
                  </title>
                </circle>
              ))}
            </g>
          );
        })}
        {labels.map((label, index) =>
          index % labelEvery === 0 || index === labels.length - 1 ? (
            <text
              key={`${label}-${index}`}
              x={xFor(label)}
              y={height - 18}
              textAnchor="middle"
              className="app-chart-axis"
            >
              {label.length > 14 ? `${label.slice(0, 13)}…` : label}
            </text>
          ) : null,
        )}
      </svg>
      {multiple ? (
        <ul className="app-chart-legend">
          {series.map(([name], index) => (
            <li key={`${name}-${index}`}>
              <span
                className="app-chart-swatch"
                style={{ background: PALETTE[index % PALETTE.length] }}
              />
              <span className="app-chart-legend-label" title={name}>
                {name || "—"}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function PieChart({ data }: { data: ChartPoint[] }) {
  const format = useNumberFormatter();
  const { lang } = useI18n();
  const positive = data.filter((point) => point.value > 0);
  const total = positive.reduce((sum, point) => sum + point.value, 0);
  if (total <= 0) {
    return <BarChart data={data} />;
  }

  const shares = positive.map((point) => (point.value / total) * 100);
  const items = positive.map((point, index) => {
    const start = shares
      .slice(0, index)
      .reduce((sum, value) => sum + value, 0);
    const share = shares[index];
    const color = PALETTE[index % PALETTE.length];
    return { ...point, color, share, start, end: start + share };
  });
  const stops = items.map(
    (item) => `${item.color} ${item.start}% ${item.end}%`,
  );

  return (
    <div className="app-chart-pie">
      <div
        className="app-chart-donut"
        style={{ background: `conic-gradient(${stops.join(", ")})` }}
        role="img"
        aria-label="Pie chart"
      >
        <div className="app-chart-donut-hole">
          <span>{format.format(total)}</span>
          <small>{lang === "en" ? "Total" : "Всего"}</small>
        </div>
      </div>
      <ul className="app-chart-legend">
        {items.map((item) => (
          <li key={item.label}>
            <span
              className="app-chart-swatch"
              style={{ background: item.color }}
            />
            <span className="app-chart-legend-label" title={item.label}>
              {item.label}
            </span>
            <span className="app-chart-legend-value">
              {format.format(item.value)} · {Math.round(item.share)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Chart({ spec }: { spec: ChartSpec }) {
  const meta = [
    spec.subtitle,
    spec.value_label
      ? `${spec.value_label}${spec.unit ? `, ${spec.unit}` : ""}`
      : spec.unit,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <figure className="app-chart app-surface app-border app-round-sm">
      <figcaption className="app-chart-head">
        <div className="app-chart-title">{spec.title}</div>
        {meta ? <div className="app-chart-subtitle">{meta}</div> : null}
      </figcaption>
      {spec.type === "line" ? (
        <LineChart data={spec.data} />
      ) : spec.type === "pie" ? (
        <PieChart data={spec.data} />
      ) : (
        <BarChart data={spec.data} />
      )}
    </figure>
  );
}
