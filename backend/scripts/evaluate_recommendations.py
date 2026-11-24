"""Offline, consented labelled JSONL comparison. Never promotes a live model.

Each row: {group_id, profile_text, postings:[{id,title,description,fit_score,
matching_details:{eligibility:{status:'eligible'}}}], relevance:{posting_id:0..3}}.
One group is one independently reviewed profile/job shortlist. Keep evaluation
data private; this script prints only aggregate metrics. No downloads or APIs.
"""
import argparse
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def evaluate(groups,ranker,k):
    from app.recommendation.evaluation import metrics
    scores=[];durations=[]
    for group in groups:
        started=time.perf_counter();ids=ranker(group);durations.append((time.perf_counter()-started)*1000)
        scores.append(metrics(group['relevance'],ids,k))
    return {'metrics':{key:round(statistics.mean(v[key] for v in scores),6) for key in scores[0]},
            'latency_p95_ms':round(sorted(durations)[max(0,math.ceil(.95*len(durations))-1)],2)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset',type=Path);parser.add_argument('--reranker',type=Path);parser.add_argument('--bge',type=Path)
    parser.add_argument('--k',type=int,default=10);args=parser.parse_args()
    if not 1<=args.k<=20:parser.error('--k must be between 1 and 20')
    groups=[json.loads(line) for line in args.dataset.read_text(encoding='utf-8').splitlines() if line.strip()]
    if not groups or len({g['group_id'] for g in groups})!=len(groups):parser.error('Need non-empty independently identified groups')
    for group in groups:
        ids=[p['id'] for p in group['postings']]
        if not 1<=len(ids)<=20 or len(set(ids))!=len(ids) or set(group['relevance'])!=set(ids):parser.error('Each group needs 1..20 unique, fully labelled postings')
        if any((p.get('matching_details') or {}).get('eligibility',{}).get('status')!='eligible' for p in group['postings']):parser.error('Evaluate eligibility separately; ranking inputs must already be eligible')
        if any(type(v) is not int or not 0<=v<=3 for v in group['relevance'].values()):parser.error('Relevance labels must be integers 0..3')
    from pydantic_settings.sources import DotEnvSettingsSource
    with patch.dict(os.environ,{'APP_ENV':'test','DEBUG':'false','HF_HUB_OFFLINE':'1'}),patch.object(DotEnvSettingsSource,'__call__',return_value={}):
        from app.config import settings
        from app.recommendation.ranking import rerank,verify_manifest
        baseline=lambda g:[p['id'] for p in sorted(g['postings'],key=lambda p:(-float(p.get('fit_score') or 0),p['id']))]
        report={'groups':len(groups),'k':args.k,'baseline_v2':evaluate(groups,baseline,args.k),'promoted':False,
                'note':'Labels, independence, eligibility errors, cold-start memory and target-host latency need review. This report never changes live ranking.'}
        if args.reranker:
            settings.RERANKER_PATH=str(args.reranker.resolve())
            def cross(g):
                result=rerank(g['profile_text'],g['postings'])
                if result['status']!='experimental':raise RuntimeError('Reranker unavailable; no fallback presented as candidate quality')
                return result['ordered_ids']
            report['cross_encoder']=evaluate(groups,cross,args.k)
        if args.bge:
            verify_manifest(args.bge)
            from sentence_transformers import SentenceTransformer
            model=SentenceTransformer(str(args.bge.resolve()),device='cpu',local_files_only=True,trust_remote_code=False)
            def bge(g):
                text=[g['profile_text'][:5000]]+[p['title']+'\n'+p.get('description','')[:5000] for p in g['postings']]
                vectors=model.encode(text,normalize_embeddings=True)
                order=sorted(zip(g['postings'],vectors[1:]),key=lambda x:(-float(vectors[0]@x[1]),x[0]['id']))
                return [p['id'] for p,_ in order]
            report['bge_embeddings']=evaluate(groups,bge,args.k)
        print(json.dumps(report,indent=2))


if __name__=='__main__':main()
