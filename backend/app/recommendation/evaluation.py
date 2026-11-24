"""Offline evaluation: no account data, provider calls or production promotion."""
import math


def metrics(relevance, ordered_ids, k=10):
    ordered = ordered_ids[:k]
    positives = sum(v > 0 for v in relevance.values())
    hits = sum(relevance.get(i, 0) > 0 for i in ordered)
    dcg = sum((2**relevance.get(pid, 0)-1)/math.log2(rank+2) for rank,pid in enumerate(ordered))
    ideal = sum((2**v-1)/math.log2(rank+2) for rank,v in enumerate(sorted(relevance.values(),reverse=True)[:k]))
    return {'precision_at_k': hits/len(ordered) if ordered else 0,
            'recall_at_k': hits/positives if positives else 0, 'ndcg_at_k': dcg/ideal if ideal else 0}


def promotion_allowed(baseline, candidate, *, independently_labelled_groups, eligibility_errors, latency_ms, peak_mb):
    return bool(independently_labelled_groups >= 100 and eligibility_errors == 0 and
                candidate['ndcg_at_k'] > baseline['ndcg_at_k'] and candidate['recall_at_k'] >= baseline['recall_at_k'] and
                candidate['precision_at_k'] >= baseline['precision_at_k'] and
                latency_ms <= 2000 and peak_mb <= 1500)
