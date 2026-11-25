export type ChartPoint = {
  label: string;
  value: number;
  series?: string;
};

export type ChartSpec = {
  type: "bar" | "line" | "pie";
  title: string;
  subtitle?: string;
  category_label?: string;
  value_label?: string;
  unit?: string;
  data: ChartPoint[];
};

function text(value: unknown, limit = 300): string | undefined {
  if (typeof value !== "string") return undefined;
  const clean = value.replace(/\s+/g, " ").trim();
  return clean ? clean.slice(0, limit) : undefined;
}

export function sanitizeChart(value: unknown): ChartSpec | undefined {
  if (!value || typeof value !== "object") return undefined;
  const raw = value as Partial<ChartSpec>;
  if (
    raw.type !== "bar" &&
    raw.type !== "line" &&
    raw.type !== "pie"
  ) {
    return undefined;
  }
  const title = text(raw.title);
  if (!title || !Array.isArray(raw.data)) return undefined;

  const data = raw.data
    .map((point) => {
      if (!point || typeof point !== "object") return null;
      const label = text((point as Partial<ChartPoint>).label, 120);
      const numeric = (point as Partial<ChartPoint>).value;
      if (!label || typeof numeric !== "number" || !Number.isFinite(numeric)) {
        return null;
      }
      const series = text((point as Partial<ChartPoint>).series, 120);
      return {
        label,
        value: numeric,
        ...(series ? { series } : {}),
      };
    })
    .filter((point): point is ChartPoint => point !== null)
    .slice(0, 40);

  if (data.length === 0) return undefined;

  return {
    type: raw.type,
    title,
    ...(text(raw.subtitle) ? { subtitle: text(raw.subtitle)! } : {}),
    ...(text(raw.category_label)
      ? { category_label: text(raw.category_label)! }
      : {}),
    ...(text(raw.value_label) ? { value_label: text(raw.value_label)! } : {}),
    ...(text(raw.unit) ? { unit: text(raw.unit)! } : {}),
    data,
  };
}
