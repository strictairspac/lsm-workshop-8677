import os,time,json,traceback
from pathlib import Path
from sqlalchemy import select
from .config.database import Session
from .models.trial import Trial
from .models.reduction import Reduction
from .models.dataset import Dataset
from .models.config import Config
from .services.trial import queue
from .services.lsm_engine import simulate
from .services.reducer import advance,sample
ARTIFACTS=Path(os.getenv('ARTIFACTS_DIR','/artifacts'))
heartbeat=ARTIFACTS/'worker.heartbeat'
SLICE=200  # replays per persisted checkpoint; bounds lost work on a crash
SCAN=200000  # proof candidates a single slice may enumerate without replaying
def run_one(ident):
    with Session() as db:
        x=db.get(Trial,ident)
        if not x or x.result is not None:return
        x.status='running';db.commit()
        try:
            x.result=simulate(x.input_snapshot['entries'],x.input_snapshot['config']);x.status='passed'
        except Exception as exc:x.result={'error':str(exc)[:500]};x.status='failed'
        db.commit();(ARTIFACTS/f'lsm-trial-{ident}.json').write_text(json.dumps(x.result,ensure_ascii=False,indent=2))
def run_reduction(ident):
    with Session() as db:
        x=db.get(Reduction,ident)
        if not x or x.status in ('done','failed'):return
        state=x.search_state or {'tested':{},'best_indices':list(range(len(x.input_snapshot['entries']))),'state':{'stage':'search'}}
        entries=x.input_snapshot['entries'];fault=x.input_snapshot['fault'];config=x.input_snapshot['config']
        x.status='running';db.commit()
        def checkpoint(snap):
            x.search_state={'tested':snap['tested'],'best_indices':snap['best_indices'],'state':snap['state']}
            db.commit()
        try:
            snap=advance(entries,config,fault,x.target,x.budget,state.get('tested'),state.get('best_indices'),state.get('state'),max_tests=SLICE,max_scan=SCAN,checkpoint=checkpoint)
            x.search_state={'tested':snap['tested'],'best_indices':snap['best_indices'],'state':snap['state']}
            sample_entries=sample(entries,snap['best_indices'])
            proved=snap['status']=='done'
            x.result={'sample':sample_entries,'sample_indices':snap['best_indices'],'sample_size':len(sample_entries),'original_size':len(entries),'proven_shortest':proved,'exhausted':snap['status']=='exhausted','message':snap['message'],'stage':snap['state'].get('stage'),'target':x.target,'replays_used':len(snap['tested']),'budget':x.budget,'input_snapshot':x.input_snapshot,'first_divergence_after_replay':None}
            replayed=simulate(sample_entries,config,fault)
            x.result['first_divergence_after_replay']=replayed.get('first_divergence')
            x.result['replay_matches_target']=x.result['first_divergence_after_replay']==x.target
            x.status={'done':'done','exhausted':'exhausted'}.get(snap['status'],'running')
            if x.status=='running':queue.rpush('lsm:reductions',ident)
            if x.status=='exhausted':x.result['note']='重放额度用完，当前样本已保存；追加额度后从中断处继续，已测候选不重复扣次数。'
        except Exception as exc:x.result={'error':str(exc)[:500]};x.status='failed'
        db.commit();(ARTIFACTS/f'lsm-reduction-{ident}.json').write_text(json.dumps(x.result,ensure_ascii=False,indent=2))
def main():
    while True:
        try:
            heartbeat.write_text(str(time.time()));item=queue.blpop(['lsm:jobs','lsm:reductions'],timeout=2)
            if item:
                name,raw=item[0],item[1]
                if name==b'lsm:jobs':run_one(int(raw))
                else:run_reduction(int(raw))
            else:
                with Session() as db:
                    pending=list(db.scalars(select(Trial.id).where(Trial.status.in_(['queued','running']))))
                    pending_reductions=list(db.scalars(select(Reduction.id).where(Reduction.status.in_(['queued','running']))))
                for ident in pending:run_one(ident)
                for ident in pending_reductions:run_reduction(ident)
        except Exception:traceback.print_exc();time.sleep(2)
if __name__=='__main__':main()
