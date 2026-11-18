import { notFound } from "next/navigation";
import { AlertForm } from "@/components/AlertForm";
import { PriceChart } from "@/components/PriceChart";
import { api, clp } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const pid = Number(id);
  if (!Number.isInteger(pid)) notFound();
  const p = await api.product(pid).catch(() => null);
  if (!p) notFound();
  const s = p.stats;

  return (
    <>
      <h1>{p.name}</h1>
      <p className="sub">
        {p.size}
        {p.brand ? ` · ${p.brand}` : ""} · {p.offers.length} tiendas
      </p>

      {s && (
        <div className="kpis">
          <div className="card kpi">
            <div className="label">Mejor precio hoy</div>
            <div className="value">{clp(s.current)}</div>
          </div>
          <div className="card kpi">
            <div className="label">Mínimo 90 días</div>
            <div className="value">{clp(s.min_90d)}</div>
          </div>
          <div className="card kpi">
            <div className="label">Mediana 30 días</div>
            <div className="value">{clp(s.median_30d)}</div>
          </div>
          <div className="card kpi">
            <div className="label">Tendencia</div>
            <div className="value">
              {s.trend_pct_week > 0 ? "+" : ""}
              {s.trend_pct_week.toFixed(1)}%<span className="muted"> /sem</span>
            </div>
          </div>
        </div>
      )}

      <div className="two-col" style={{ marginTop: 16 }}>
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Historial por tienda (90 días)</h2>
          <PriceChart series={p.series} stores={p.stores} min90={s?.min_90d} />
        </div>
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Alerta de precio</h2>
          <AlertForm productId={p.id} suggested={s ? Math.round(s.min_90d) : undefined} />
        </div>
      </div>

      <h2>Precios actuales</h2>
      <div className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th>Tienda</th>
              <th>Nombre en la tienda</th>
              <th className="num">Precio</th>
              <th className="num">Precio normal</th>
              <th>Visto</th>
            </tr>
          </thead>
          <tbody>
            {p.offers.map((o) => (
              <tr key={o.store}>
                <td>{o.store_name}</td>
                <td className="muted">{o.raw_name}</td>
                <td className="num">{clp(o.price)}</td>
                <td className="num">{o.list_price ? <s>{clp(o.list_price)}</s> : "–"}</td>
                <td>{o.observed_on}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
