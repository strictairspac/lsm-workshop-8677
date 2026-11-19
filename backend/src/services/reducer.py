"""Deterministic, resumable reducer for the read-error workshop.

A reduction looks for the shortest subsequence of a dataset's operations that,
replayed in the original order with the same config and simulated fault, shows
the exact same first divergence as the full batch: phase, key, expected value
and actual value. The search shrinks chunks greedily and then proves minimality
by enumerating every shorter subsequence. Every distinct candidate is evaluated
at most once per reduction and charged once against the replay budget; retrying
a candidate after an interruption reuses the cached verdict, so it is not
charged twice.

This module is pure: no database, Redis or wall clock. The worker persists the
returned state so a reduction can be resumed exactly where it stopped.
"""
import hashlib
import json
from math import comb

from .lsm_engine import simulate

DIVERGENCE_FIELDS=('phase','key','expected','actual')
STAGE_LABELS={'search':'收缩候选','proof':'证明最短','done':'已完成'}

class BudgetExhausted(Exception):
    """No replay budget is left for an uncached candidate."""

def canonical(entries):
    return hashlib.sha256(json.dumps(entries,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def reproduces(result,target):
    d=result.get('first_divergence')
    return bool(d) and all(d.get(f)==target.get(f) for f in DIVERGENCE_FIELDS)

def first_divergence(entries,config,fault):
    """The first divergence of the full batch; also the reduction target."""
    return simulate(entries,config,fault).get('first_divergence')

def sample(entries,indices):
    return [entries[i] for i in indices]

def unrank_combination(n,length,rank):
    """The `rank`-th k-subset of range(n) in lexicographic combination order."""
    result=[];start=0
    for slot in range(length):
        remaining=length-slot-1
        for value in range(start,n):
            block=comb(n-value-1,remaining)
            if rank<block:
                result.append(value);start=value+1;break
            rank-=block
    return tuple(result)

def may_replicate(entries,indices,target):
    """Cheap necessary condition: a candidate must contain an operation on the
    target key. A subsequence without one cannot make that key diverge. This
    deliberately does not prune on the key's last position: the stale-version
    fault can carry an older record down the levels, so a sample that stops
    before the key's final write can still reproduce the wrong value."""
    if not indices:return False
    key=target.get('key')
    return any(entries[i]['key']==key for i in indices)

def _stage_message(state):
    stage=state.get('stage')
    if stage=='search':return '正在贪心删除整段操作'
    if stage=='proof':return '正在枚举更短子序列以证明最短'
    return '已完成'

def advance(entries,config,fault,target,budget,tested=None,best_indices=None,state=None,max_tests=None,checkpoint=None,max_scan=200000):
    """Run until done, budget exhausted or `max_tests` new replays happened.

    `tested` maps a canonical candidate digest to its verdict and is the only
    thing that counts against `budget`; candidates already present are never
    replayed or charged again. `state` carries the resumable cursor.
    `checkpoint` (optional) is called with the latest snapshot after each new
    replay so a crash mid-reduction cannot double-charge a candidate.
    `max_scan` bounds how many proof candidates one call may skip/enumerate, so
    a large space cannot hold the worker indefinitely.
    """
    tested=dict(tested or {})
    best=list(best_indices) if best_indices is not None else list(range(len(entries)))
    state=dict(state or {'stage':'search'})
    evals=0;scanned=0

    def snapshot(status,message):
        return {'tested':tested,'best_indices':list(best),'state':dict(state),'status':status,'message':message,'evaluations':evals}

    def test(indices):
        nonlocal evals
        sub=[entries[i] for i in indices]
        key=canonical(sub)
        if key in tested:return tested[key]
        if len(tested)>=budget:raise BudgetExhausted()
        try:verdict=reproduces(simulate(sub,config,fault),target)
        except ValueError:verdict=False
        tested[key]=verdict
        evals+=1
        if checkpoint:checkpoint(snapshot('running',_stage_message(state)))
        return verdict

    try:
        while True:
            if (max_tests is not None and evals>=max_tests) or scanned>=max_scan:
                return snapshot('running',_stage_message(state))
            stage=state.get('stage')
            if stage=='done':
                return snapshot('done','已证明最短：没有任何更短子序列能重现同一处读错')
            if stage=='search':
                n=len(best)
                if n<=1:
                    state={'stage':'done'}
                    continue
                chunk=int(state.get('chunk') or max(1,n//2))
                cursor=int(state.get('cursor',0))
                if cursor>=n:
                    if chunk<=1:
                        state={'stage':'proof','length':1,'combo':0}
                    else:
                        state={'stage':'search','chunk':max(1,chunk//2),'cursor':0}
                    continue
                chunk=min(chunk,n-cursor)
                cand=best[:cursor]+best[cursor+chunk:]
                if not cand:
                    state={'stage':'search','chunk':chunk,'cursor':n}
                    continue
                if test(cand):
                    best=cand
                    state={'stage':'search','chunk':max(1,len(cand)//2),'cursor':0}
                else:
                    state={'stage':'search','chunk':chunk,'cursor':cursor+chunk}
                continue
            if stage=='proof':
                k=len(best)
                length=int(state.get('length',1))
                combo=int(state.get('combo',0))
                if k<=1 or length>=k:
                    state={'stage':'done'}
                    continue
                total=comb(len(entries),length)
                if combo>=total:
                    state={'stage':'proof','length':length+1,'combo':0}
                    continue
                cand=unrank_combination(len(entries),length,combo)
                scanned+=1
                if not may_replicate(entries,cand,target):
                    state={'stage':'proof','length':length,'combo':combo+1}
                    continue
                if test(cand):
                    best=list(cand)
                    state={'stage':'proof','length':1,'combo':0}
                else:
                    state={'stage':'proof','length':length,'combo':combo+1}
                continue
            raise ValueError('未知的缩减阶段')
    except BudgetExhausted:
        return snapshot('exhausted','重放额度已用完（累计 %d 次尝试，额度 %d 次）；当前样本能否保证最短尚未证明'%(len(tested),budget))
