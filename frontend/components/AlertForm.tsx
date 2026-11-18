"use client";

import { useState } from "react";

export function AlertForm({ productId, suggested }: { productId: number; suggested?: number }) {
  const [email, setEmail] = useState("");
  const [target, setTarget] = useState(suggested ? String(suggested) : "");
  const [status, setStatus] = useState<"idle" | "sending" | "ok" | "error">("idle");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("sending");
    const res = await fetch("/api/alerts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        product_id: productId,
        target_price: target ? Number(target.replace(/\D/g, "")) : null,
      }),
    });
    setStatus(res.ok ? "ok" : "error");
  }

  return (
    <form className="form" onSubmit={submit}>
      <input type="email" required placeholder="tu@correo.cl" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input
        inputMode="numeric"
        placeholder="Precio objetivo (opcional)"
        value={target}
        onChange={(e) => setTarget(e.target.value)}
      />
      <button disabled={status === "sending"}>Avisarme si baja</button>
      {status === "ok" && <span className="ok">Listo: te avisaremos por correo.</span>}
      {status === "error" && <span className="err">No se pudo crear la alerta.</span>}
      <span className="muted">
        Se avisa al alcanzar el precio objetivo, un mínimo de 90 días o una caída ≥10% vs. la mediana de 30 días.
      </span>
    </form>
  );
}
