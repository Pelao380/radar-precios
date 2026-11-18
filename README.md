# Radar de precios 🇨🇱

Sistema que recolecta precios de supermercados chilenos de forma periódica, los
normaliza y deduplica entre tiendas, guarda el historial en PostgreSQL y lo
muestra en un dashboard con búsqueda en lenguaje natural y alertas por correo.

> «¿Dónde está más barato el aceite de 1 L esta semana?»
> → *El más barato esta semana es {producto} (1 L) en {tienda} a {precio}. En otras tiendas: …*
> (respuesta armada con una plantilla a partir de filas SQL; ver §4)

| Capa | Tecnología |
|---|---|
| Jobs programados | Celery + Redis (beat cada 6 h, reintentos con backoff, rate limit global en Redis, caché HTTP) |
| Datos | PostgreSQL 16 + pgvector, ELT bronze → silver → gold, vista materializada de estadísticas |
| IA | Deduplicación con embeddings + búsqueda en lenguaje natural con Claude (salida estructurada) |
| API | FastAPI |
| Frontend | Next.js 15 (App Router) + TypeScript + Recharts |
| Calidad | pytest (unitarios + integración con Postgres real), ruff, GitHub Actions, Docker Compose |

## Arquitectura

```mermaid
flowchart LR
  beat[Celery beat<br/>cada 6 h] --> scrape
  subgraph cola [Redis + Celery]
    scrape[scrape_store ×4<br/>reintentos · rate limit] --> etl[process_snapshot<br/>cola etl, concurrencia 1]
    etl --> alerts[refresh_and_alert]
  end
  scrape -- JSON crudo --> raw[(raw_snapshots<br/>bronze)]
  etl -- normaliza + embedding --> listings[(listings<br/>silver)]
  etl -- pgvector kNN --> products[(products<br/>gold)]
  etl --> obs[(price_observations)]
  alerts --> mv[(product_stats<br/>vista materializada)]
  alerts -- SMTP --> mail[Correo]
  api[FastAPI] --> products & obs & mv
  api -- intención --> claude[Claude API]
  web[Next.js] --> api
```

## Decisiones de diseño

### 1. Fuentes: adaptadores más una fuente simulada honesta

Los endpoints públicos de catálogo (VTEX `catalog_system`) de las cadenas chilenas
probadas respondieron **403/404** a clientes automáticos (nov. 2026). En vez de
pelear con un antibot, cosa que además suele ir contra los términos de uso, cada
tienda es un adaptador (`radar/sources/`):

- `SimulatedSource`: genera 40 productos × 4 tiendas con una caminata aleatoria,
  estacionalidad, inflación diaria y promociones periódicas. Está **sembrada por
  (tienda, sku, día)**: el mismo día siempre da los mismos precios, así que los
  tests y la demo son reproducibles.
- `VtexSource`: adaptador real y testeado contra respuestas VTEX simuladas. Se
  activa con `SOURCE_MODE=vtex` y `VTEX_BASE_URL_<TIENDA>` cuando se tiene un
  endpoint verificado y permitido.

Cada tienda escribe los nombres a su manera (`SEMIDESC`, `S/GAS`, `G1`, `N°5`,
`PAPEL HIG`, tamaño antes o después de la marca, mayúsculas), igual que en la
realidad. Por eso la deduplicación tiene un problema real que resolver.

### 2. Cola: por qué dos colas y dónde vive el rate limit

- **`rate_limit` de Celery es por worker**, no global. Con 4 workers serían 4×
  las solicitudes. El límite por dominio vive en Redis (`INCR` + `EXPIRE`, ventana
  de 60 s) y lo comparten todos los workers (`radar/http.py`).
- **Caché HTTP en Redis** (TTL 30 min): si una tarea se reintenta, no vuelve a
  golpear a la tienda.
- **Reintentos** con backoff exponencial y *jitter* solo para errores
  transitorios (429, 5xx, timeouts). Un 404 no se reintenta.
- **Scraping y ETL separados**: el JSON crudo se guarda primero (bronze), así
  que un fallo del ETL o de la API de embeddings nunca obliga a volver a scrapear.
  `process_snapshot` es idempotente (upsert por `(listing_id, día)`), así que
  `acks_late` + re-entrega no duplican datos.
- **El ETL va en la cola `etl` con concurrencia 1**: si dos tiendas traen a la vez
  un producto nuevo, dos ETL en paralelo crearían dos productos canónicos. Los
  scrapers, que son lo lento, sí corren en paralelo.

### 3. Deduplicación: medida, no supuesta

El mismo aceite aparece como `Aceite Vegetal Belmont 1 L` (Lider),
`Aceite Belmont Vegetal 1lt` (Jumbo) y `ACEITE VEGETAL BELMONT 1 LITRO` (Unimarc).
El algoritmo (`radar/matching.py`):

1. **Normalización** (`radar/normalize.py`): tildes, sinónimos (`maravilla` → `girasol`),
   abreviaturas (`S/` → `sin`) y tamaño a unidad base (`1 LITRO` = `1lt` = 1000 ml;
   `6 x 350 ml` = 2100 ml).
2. **Blocking por tamaño**: un 1 L nunca se fusiona con 900 ml (precios distintos).
3. **Marca** compatible.
4. **Atributos en conflicto**, como restricción dura: `sin gas`/`con gas`,
   `entera`/`descremada`, `zero`/`original`…
5. **Similitud coseno** de embeddings ≥ umbral, buscando los vecinos con un
   índice HNSW de pgvector.

Evaluación sobre las 160 fichas, con verdad-terreno conocida (`python -m eval.eval_dedup --sweep`).
Métrica: precisión, recall y F1 sobre pares de fichas.

| Método | Precisión | Recall | F1 | Productos |
|---|---:|---:|---:|---:|
| Nombre exacto | 1.000 | 0.008 | 0.017 | 158 |
| Reglas (clave normalizada) | 1.000 | 0.725 | 0.841 | 63 |
| Fuzzy (difflib ≥ 0.85) | 0.888 | 0.858 | 0.873 | 47 |
| **Embeddings + reglas duras (0.75)** | **1.000** | **0.921** | **0.959** | 47 |

*(40 productos reales.)* Lo que enseñó la evaluación:

- **Encontró dos bugs** en la primera versión de la normalización: los números
  sueltos se borraban (`Grado 1` = `Grado 2`) y `sin`/`con` eran *stopwords*
  (`Sin gas` = `Con gas`). Ambos son fusiones falsas, el peor error posible en
  un comparador de precios, y quedaron como tests de regresión.
- **Los embeddings solos no bastan**: `agua sin gas` y `agua con gas` difieren en
  una palabra y son casi idénticos para cualquier embedding. La regla de
  conflictos subió la precisión de 0.93 a 1.00 (con umbral 0.80).
- **El umbral prioriza precisión**. Con 0.70 el F1 es mayor (0.979), pero aparecen
  fusiones falsas (P = 0.983). Partir un producto en dos solo duplica una tarjeta;
  fusionar dos distintos muestra un precio equivocado.
- ⚠️ El umbral se ajustó sobre el mismo conjunto que se reporta, así que estas
  cifras son optimistas. Con datos reales habría que etiquetar un conjunto de
  prueba aparte.

El embedder por defecto es un *hashing embedder* de n-gramas de caracteres:
local, determinista, gratis y suficiente para nombres cortos con abreviaturas.
`EMBEDDINGS_PROVIDER=voyage` usa Voyage AI con la misma dimensión (512), sin
migrar la columna, y `eval_dedup --provider voyage` compara ambos.

### 4. Búsqueda en lenguaje natural: el LLM no ve precios

```
pregunta → Claude (salida estructurada: producto, tamaño, tienda, periodo, orden)
         → embedding + pgvector → SQL → plantilla de respuesta
```

Claude solo **traduce** la pregunta a filtros validados con un esquema Pydantic
(`radar/intent.py`). Los precios y la respuesta salen de SQL y de una plantilla,
así que **cada número que ve el usuario es trazable a una observación**: el modelo
no puede alucinar un precio. Si no hay `ANTHROPIC_API_KEY`, o si la llamada
falla, un parser de reglas hace lo mismo con menos cobertura y la búsqueda nunca
se cae por la IA. La interfaz muestra qué parser interpretó la pregunta.

### 5. Estadísticas

- **Mínimo de 90 días**, máximo y mediana de 30 días, sobre el *mejor precio
  diario entre tiendas*, en la vista materializada `product_stats`, que se
  refresca con `CONCURRENTLY` tras cada ETL para no bloquear lecturas.
- **Tendencia**: pendiente de una regresión lineal de 30 días, en % por semana.
- **Alertas** (`radar/stats.py::detect_drop`), en orden de prioridad: precio
  objetivo del usuario → mínimo de 90 días → caída ≥ 10% vs. la mediana de 30 días.
  Son idempotentes: `UNIQUE(subscription_id, día)` y el correo se envía solo si
  el `INSERT` insertó. Si el SMTP falla, se borra el registro para reintentar.

## Correr localmente

Requiere Docker Desktop.

```bash
cp .env.example .env
docker compose up --build
```

- Dashboard: http://localhost:3000
- API y Swagger: http://localhost:8000/docs
- Correos de alertas (Mailpit): http://localhost:8025

La primera vez, el servicio `seed` crea el esquema y carga 120 días de historial
simulado con el mismo ETL que usa la cola. Para forzar un scraping ahora:

```bash
docker compose exec api python -m radar.cli scrape
```

### Tests

```bash
cd backend
pip install -e ".[dev]"
pytest                                   # unitarios; los de integración se saltan sin DB
DATABASE_URL=postgresql+psycopg://radar:radar@localhost:5432/radar_test pytest   # base aparte: los tests la borran
python -m eval.eval_dedup --sweep
```

CI (GitHub Actions) corre lint, tests unitarios y de integración contra
`pgvector/pgvector:pg16`, la evaluación de deduplicación (en el resumen del job),
typecheck y build de Next.js, y `docker compose build`.

## Despliegue (demo 24/7)

Docker Compose sirve para desarrollo: solo está en línea mientras tu PC lo esté.
Para una demo pública se usa el mismo código con otras variables de entorno:

| Pieza | Servicio sugerido | Variable |
|---|---|---|
| PostgreSQL + pgvector | Neon | `DATABASE_URL` (se acepta `postgresql://…`) |
| Redis | Upstash | `REDIS_URL` (`rediss://…?ssl_cert_reqs=required`, que Celery exige con TLS) |
| API | Render / Fly.io (Dockerfile de `backend/`) | — |
| Worker + beat | Un solo proceso: `celery -A radar.tasks worker -B -Q celery,etl -c 1` | — |
| Dashboard | Vercel (carpeta `frontend/`) | `API_URL` |

Después del primer deploy: `python -m radar.cli backfill --days 120`.

## Estructura

```
backend/
  radar/
    sources/      adaptadores de tienda (simulada, VTEX) + catálogo
    normalize.py  limpieza de nombres y tamaños (puro)
    matching.py   embeddings + decisión de deduplicación (puro)
    stats.py      mínimos, tendencias, alertas (puro)
    intent.py     pregunta → filtros (Claude o reglas)
    http.py       cliente con caché y rate limit en Redis
    etl.py        snapshot → fichas → productos → historial
    tasks.py      Celery: jobs, reintentos, colas
    api.py        FastAPI
  eval/           evaluación de deduplicación
  tests/
frontend/         Next.js + TypeScript
```

## Limitaciones conocidas

- Los datos de la demo son simulados (ver §1). El adaptador VTEX no se ha
  probado contra un sitio real.
- La evaluación de deduplicación usa el mismo conjunto para ajustar y reportar.
- Un producto nuevo cuyo vecino correcto no queda entre los 5 más cercanos del
  bloque no se fusiona (ocurre en recall, no en precisión).
- Sin autenticación: cualquiera puede suscribir un correo a alertas. Antes de
  una demo pública conviene agregar confirmación por correo (double opt-in).
