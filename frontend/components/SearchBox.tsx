"use client";

import Link from "next/link";
import { useState } from "react";
import { clp, type SearchResult } from "@/lib/api";

const EXAMPLES = [
  "¿Dónde está más barato el aceite de 1 L esta semana?",
  "leche descremada en Santa Isabel hoy",
  "qué ofertas de café hay este mes",
  "arroz grado 1 a menos de $1.800",
];

export function SearchBox() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResult | null>(null);

  async function run(q: string) {
    if (q.trim().length < 2) return;
    setQuery(q);
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q }),
      });
      if (!res.ok) throw new Error(`Error ${res.status}`);
      setResult((await res.json()) as SearchResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error desconocido");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      <form
        className="search"
        onSubmit={(e) => {
          e.preventDefault();
          run(query);
        }}
      >
        <input
          aria-label="Pregunta"
          placeholder="Pregunta en lenguaje natural…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button disabled={loading}>{loading ? "Buscando…" : "Buscar"}</button>
      </form>
      <div className="examples">
        {EXAMPLES.map((ex) => (
          <button key={ex} type="button" onClick={() => run(ex)}>
            {ex}
          </button>
        ))}
      </div>
      {error && <p className="err">{error}</p>}
      {result && (
        <div className="answer">
          <p>{result.answer}</p>
          <div className="intent">
            interpretado por {result.intent.parser === "llm" ? "Claude" : "reglas"}: producto=&quot;
            {result.intent.product}&quot;
            {result.intent.size_qty ? ` tamaño=${result.intent.size_qty}${result.intent.size_unit}` : ""}
            {result.intent.store ? ` tienda=${result.intent.store}` : ""}
            {result.intent.max_price ? ` máx=${result.intent.max_price}` : ""} días={result.intent.period_days} orden=
            {result.intent.sort}
          </div>
          {result.results.length > 0 && (
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table>
                <thead>
                  <tr>
                    <th>Producto</th>
                    <th>Tienda</th>
                    <th className="num">Precio actual</th>
                    <th className="num">Mín. periodo</th>
                  </tr>
                </thead>
                <tbody>
                  {result.results.slice(0, 10).map((r) => (
                    <tr key={`${r.product_id}-${r.store}`}>
                      <td>
                        <Link href={`/productos/${r.product_id}`}>
                          {r.canonical_name} <span className="muted">{r.size_label}</span>
                        </Link>
                      </td>
                      <td>{r.store_name}</td>
                      <td className="num">{clp(r.last_price)}</td>
                      <td className="num">{clp(r.min_price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
