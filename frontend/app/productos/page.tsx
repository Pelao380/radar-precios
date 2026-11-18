import { ProductCard } from "@/components/ProductCard";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Products({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q } = await searchParams;
  const products = await api.products(q);
  return (
    <>
      <h1>Productos</h1>
      <p className="sub">Cada producto agrupa las fichas de todas las tiendas que lo venden.</p>
      <form className="search" style={{ marginBottom: 16 }}>
        <input name="q" defaultValue={q} placeholder="Filtrar por nombre o marca…" aria-label="Filtrar" />
        <button>Filtrar</button>
      </form>
      <div className="grid">
        {products.map((p) => (
          <ProductCard key={p.id} p={p} />
        ))}
      </div>
    </>
  );
}
