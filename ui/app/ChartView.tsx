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
  const max = Math.max(...data.map((point) => point.value), 1);
  const step = data.length > 1 ? innerW / (data.length - 1) : 0;
  const points = data.map((point, index) => ({
    ...point,
    x: padding.left + index * step,
    y: padding.top + innerH - (point.value / max) * innerH,
  }));
  const path = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${point.x},${point.y}`)
    .join(" ");
  const labelEvery = Math.max(1, Math.ceil(data.length / 6));

  return (
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
      <path d={path} className="app-chart-line" />
      {points.map((point, index) => (
        <g key={`${point.label}-${index}`}>
          <circle cx={point.x} cy={point.y} r="4" className="app-chart-point">
            <title>
              {point.label}: {format.format(point.value)}
            </title>
          </circle>
          {index % labelEvery === 0 || index === points.length - 1 ? (
            <text
              x={point.x}
              y={height - 18}
              textAnchor="middle"
              className="app-chart-axis"
            >
              {point.label.length > 14
                ? `${point.label.slice(0, 13)}…`
                : point.label}
            </text>
          ) : null}
        </g>
      ))}
    </svg>
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
