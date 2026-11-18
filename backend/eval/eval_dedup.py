"""Evaluación offline de la deduplicación entre tiendas.

Compara cuatro estrategias sobre las fichas del catálogo (40 productos × 4
tiendas = 160 fichas), cuya verdad-terreno se conoce:

  exact      nombre crudo en minúsculas y sin tildes (línea base ingenua)
  rules      clave (marca, nombre limpio, tamaño) tras normalizar
  fuzzy      difflib.SequenceMatcher sobre marca+nombre, con blocking por tamaño
  embedding  similitud coseno de embeddings, con blocking por tamaño y marca

Métrica: precisión / recall / F1 sobre *pares* de fichas (la estándar en
entity resolution). Precisión baja = fusionamos productos distintos (peor
error: comparar leche entera con descremada). Recall bajo = el mismo producto
queda partido en varios.

Uso:  python -m eval.eval_dedup [--provider hashing|voyage] [--sweep]
"""

from __future__ import annotations

import argparse
import itertools
from difflib import SequenceMatcher

from radar.embeddings import get_embedder
from radar.matching import DEFAULT_THRESHOLD, cluster
from radar.normalize import normalize, strip_accents
from radar.sources.simulated import ground_truth


def pair_metrics(pred: list, truth: list) -> tuple[float, float, float]:
    tp = fp = fn = 0
    for i, j in itertools.combinations(range(len(truth)), 2):
        same_pred, same_true = pred[i] == pred[j], truth[i] == truth[j]
        tp += same_pred and same_true
        fp += same_pred and not same_true
        fn += same_true and not same_pred
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f1


def by_key(keys: list) -> list[int]:
    ids: dict = {}
    return [ids.setdefault(k, len(ids)) for k in keys]


def fuzzy_cluster(items, threshold=0.85) -> list[int]:
    reps: list = []
    labels = []
    for p in items:
        best, best_s = None, 0.0
        for idx, r in enumerate(reps):
            if (r.size_qty, r.size_unit) != (p.size_qty, p.size_unit):
                continue
            s = SequenceMatcher(None, p.match_text, r.match_text).ratio()
            if s > best_s:
                best, best_s = idx, s
        if best is not None and best_s >= threshold:
            labels.append(best)
        else:
            labels.append(len(reps))
            reps.append(p)
    return labels


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="hashing")
    ap.add_argument("--sweep", action="store_true")
    args = ap.parse_args()

    rows = ground_truth()
    truth = [k for _, _, k in rows]
    items = [normalize(name) for _, name, _ in rows]
    embed = get_embedder(args.provider)

    results = {
        "exact": by_key([strip_accents(n).lower().strip() for _, n, _ in rows]),
        "rules": by_key([(p.brand, p.clean_name, p.size_qty, p.size_unit) for p in items]),
        "fuzzy (0.85)": fuzzy_cluster(items),
        f"embedding/{args.provider} ({DEFAULT_THRESHOLD})": cluster(items, embed.embed_one),
    }
    print(f"{len(rows)} fichas, {len(set(truth))} productos reales\n")
    print(f"{'método':32} {'precisión':>10} {'recall':>8} {'F1':>6} {'clusters':>9}")
    for name, pred in results.items():
        p, r, f1 = pair_metrics(pred, truth)
        print(f"{name:32} {p:10.3f} {r:8.3f} {f1:6.3f} {len(set(pred)):9d}")

    if args.sweep:
        print("\nbarrido de umbral (embedding):")
        for t in [0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]:
            p, r, f1 = pair_metrics(cluster(items, embed.embed_one, t), truth)
            print(f"  t={t:.2f}  P={p:.3f}  R={r:.3f}  F1={f1:.3f}")

    # errores del método de embeddings, para inspección
    pred = results[f"embedding/{args.provider} ({DEFAULT_THRESHOLD})"]
    print("\nfusiones incorrectas (embedding):")
    seen = set()
    for i, j in itertools.combinations(range(len(rows)), 2):
        if pred[i] == pred[j] and truth[i] != truth[j] and (truth[i], truth[j]) not in seen:
            seen.add((truth[i], truth[j]))
            print(f"  {rows[i][1]!r} ~ {rows[j][1]!r}")


if __name__ == "__main__":
    main()
