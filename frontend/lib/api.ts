// Tipos y llamadas a la API de FastAPI. Solo se usa en el servidor: el navegador
// habla con las rutas /api/* de Next, que hacen de proxy (sin CORS ni URLs públicas).

export const API_URL = process.env.API_URL ?? "http://localhost:8000";

export type ProductSummary = {
  id: number;
  name: string;
  brand: string | null;
  size: string;
  best_price: number;
  best_store: string;
  n_stores: number;
  min_90d: number;
  max_90d: number;
  median_30d: number | null;
  drop_pct: number;
  is_lowest_90d: boolean;
};

export type Offer = {
  store: string;
  store_name: string;
  price: number;
  list_price: number | null;
  observed_on: string;
  url: string | null;
  raw_name: string;
};

export type SeriesPoint = { day: string; best: number } & Record<string, number | string>;

export type PriceStats = {
  current: number;
  min_90d: number;
  max_90d: number;
  median_30d: number;
  trend_pct_week: number;
  is_lowest_90d: boolean;
  drop_pct_vs_median: number;
};

export type ProductDetail = {
  id: number;
  name: string;
  brand: string | null;
  size: string;
  offers: Offer[];
  stores: { slug: string; name: string }[];
  series: SeriesPoint[];
  stats: PriceStats | null;
};

export type Overview = {
  products: number;
  listings: number;
  observations: number;
  stores: number;
  since: string | null;
  last_day: string | null;
  dedup_ratio: number | null;
};

export type SearchResult = {
  query: string;
  answer: string;
  intent: {
    product: string;
    size_qty: number | null;
    size_unit: string | null;
    store: string | null;
    max_price: number | null;
    period_days: number;
    sort: "cheapest" | "biggest_drop";
    parser: "llm" | "rules";
  };
  results: {
    product_id: number;
    canonical_name: string;
    size_label: string;
    store: string;
    store_name: string;
    min_price: number;
    max_price: number;
    last_price: number;
    last_seen: string;
    similarity: number;
    drop_pct?: number;
  }[];
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { next: { revalidate: 300 } });
  if (!res.ok) throw new Error(`API ${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  overview: () => get<Overview>("/overview"),
  deals: (limit = 12) => get<ProductSummary[]>(`/deals?limit=${limit}`),
  products: (q?: string) => get<ProductSummary[]>(`/products${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  product: (id: number) => get<ProductDetail>(`/products/${id}`),
};

export const clp = (n: number) =>
  new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 }).format(n);
