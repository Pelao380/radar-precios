import Link from "next/link";
import { clp, type ProductSummary } from "@/lib/api";

export function ProductCard({ p }: { p: ProductSummary }) {
  return (
    <Link href={`/productos/${p.id}`} className="card product-card">
      <div className="name">{p.name}</div>
      <div className="meta">
        {p.size} · {p.n_stores} {p.n_stores === 1 ? "tienda" : "tiendas"}
      </div>
      <div className="price">{clp(p.best_price)}</div>
      <div className="meta">en {p.best_store} · mín. 90 días {clp(p.min_90d)}</div>
      <div>
        {p.is_lowest_90d ? (
          <span className="badge">Mínimo de 90 días</span>
        ) : p.drop_pct >= 5 ? (
          <span className="badge">-{p.drop_pct.toFixed(0)}% vs. mediana</span>
        ) : null}
      </div>
    </Link>
  );
}
