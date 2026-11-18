// Se muestra mientras el servidor espera a la API. En la demo gratuita la API
// "duerme" tras 15 minutos sin visitas y tarda cerca de un minuto en despertar.
export default function Loading() {
  return (
    <div className="card" style={{ marginTop: 24 }}>
      <p style={{ margin: 0, fontWeight: 600 }}>Cargando precios…</p>
      <p className="muted" style={{ margin: "4px 0 0" }}>
        Si es la primera visita en un rato, la API del plan gratuito está despertando: puede tardar hasta un minuto.
      </p>
    </div>
  );
}
