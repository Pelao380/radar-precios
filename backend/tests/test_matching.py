from radar.matching import Candidate, attributes_conflict, cluster, cosine, decide, hashing_embed
from radar.normalize import normalize
from radar.sources.simulated import ground_truth


def _cand(pid, raw):
    p = normalize(raw)
    return Candidate(pid, p.brand, p.size_qty, p.size_unit, hashing_embed(p.match_text), p.clean_name)


def test_embedding_is_deterministic_and_normalized():
    a, b = hashing_embed("aceite vegetal"), hashing_embed("aceite vegetal")
    assert a == b
    assert abs(cosine(a, a) - 1.0) < 1e-9


def test_similar_names_are_closer_than_different_products():
    base = hashing_embed("belmont aceite vegetal")
    assert cosine(base, hashing_embed("belmont aceite vegetal botella")) > cosine(
        base, hashing_embed("carozzi fideos spaghetti")
    )


def test_decide_matches_same_product_from_other_store():
    p = normalize("ACEITE VEGETAL BELMONT 1 LITRO")
    d = decide(p, hashing_embed(p.match_text), [_cand(1, "Aceite Vegetal Belmont 1 L")])
    assert d.product_id == 1


def test_blocking_by_size_prevents_merge():
    p = normalize("Aceite Vegetal Belmont 900 ml")
    d = decide(p, hashing_embed(p.match_text), [_cand(1, "Aceite Vegetal Belmont 1 L")])
    assert d.product_id is None


def test_different_brand_prevents_merge():
    p = normalize("Leche Entera Colun 1 L")
    d = decide(p, hashing_embed(p.match_text), [_cand(1, "Leche Entera Soprole 1 L")])
    assert d.product_id is None


def test_conflicting_attributes():
    assert attributes_conflict("agua mineral sin gas", "agua mineral con gas")
    assert attributes_conflict("leche entera", "leche descrem")
    assert not attributes_conflict("leche semidesc", "leche semidescremada")
    assert not attributes_conflict("aceite vegetal", "aceite vegetal botella")


def test_cluster_on_simulated_catalog_has_no_false_merges():
    rows = ground_truth()
    labels = cluster([normalize(n) for _, n, _ in rows])
    truth = [k for _, _, k in rows]
    by_label: dict[int, set[str]] = {}
    for lab, key in zip(labels, truth):
        by_label.setdefault(lab, set()).add(key)
    # precisión: ningún cluster mezcla productos reales distintos
    assert all(len(keys) == 1 for keys in by_label.values())
    # recall razonable: menos de 1.4 clusters por producto real
    assert len(by_label) < 1.4 * len(set(truth))
