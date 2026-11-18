import { ProductCard } from "@/components/ProductCard";
import { SearchBox } from "@/components/SearchBox";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [overview, deals] = await Promise.all([api.overview(), api.deals(12)]);
  return (
    <>
      <h1>¿Dónde está más barato?</h1>
      <p className="sub">
        Precios de {overview.stores} supermercados, actualizados cada 6 horas
        {overview.last_day ? ` · último dato ${overview.last_day}` : ""}.
      </p>

      <SearchBox />

      <h2>Resumen</h2>
      <div className="kpis">
        <div className="card kpi">
          <div className="label">Productos únicos</div>
          <div className="value">{overview.products.toLocaleString("es-CL")}</div>
        </div>
        <div className="card kpi">
          <div className="label">Fichas de tiendas</div>
          <div className="value">{overview.listings.toLocaleString("es-CL")}</div>
        </div>
        <div className="card kpi">
          <div className="label">Fichas por producto (dedup)</div>
          <div className="value">{overview.dedup_ratio ?? "–"}</div>
        </div>
        <div className="card kpi">
          <div className="label">Observaciones de precio</div>
          <div className="value">{overview.observations.toLocaleString("es-CL")}</div>
        </div>
      </div>

      <h2>Caídas de precio hoy</h2>
      {deals.length === 0 ? (
        <p className="muted">Sin caídas destacadas hoy.</p>
      ) : (
        <div className="grid">
          {deals.map((p) => (
            <ProductCard key={p.id} p={p} />
          ))}
        </div>
      )}
    </>
  );
}
