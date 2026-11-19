from sqlalchemy import select
from fastapi import HTTPException
from redis import Redis
from ..config.settings import REDIS_URL
from ..models.reduction import Reduction
from ..models.dataset import Dataset
from ..models.config import Config
from ..constants.enums import REDUCTION_STATUSES
from .config import serialize as config_dict
from .reducer import first_divergence
from .lsm_engine import simulate
queue=Redis.from_url(REDIS_URL)
def serialize(x,full=True):
    out={'id':x.id,'name':x.name,'dataset_id':x.dataset_id,'config_id':x.config_id,'fault':x.fault,'budget':x.budget,'status':x.status,'created_at':str(x.created_at),'target':x.target,'result':x.result}
    if full:
        out['input_snapshot']=x.input_snapshot
        out['search_state']=x.search_state
    else:
        out['original_size']=len(x.input_snapshot.get('entries',[]))
    return out
def listing(db):return [serialize(x,False) for x in db.scalars(select(Reduction).order_by(Reduction.id.desc()))]
def detail(db,ident):
    x=db.get(Reduction,ident)
    if not x:raise HTTPException(404,'缩减任务不存在')
    return serialize(x)
def create(db,data):
    dataset=db.get(Dataset,data.dataset_id);config=db.get(Config,data.config_id)
    if not dataset or not config:raise HTTPException(404,'写入批次或存储配置不存在')
    if db.scalar(select(Reduction).where(Reduction.name==data.name)):raise HTTPException(409,'缩减任务名称已存在')
    entries=dataset.entries;cfg=config_dict(config)
    target=first_divergence(entries,cfg,data.fault)
    if target is None:raise HTTPException(422,'该批次的完整操作在此模拟故障下没有读错，无需缩减')
    x=Reduction(name=data.name,dataset_id=data.dataset_id,config_id=data.config_id,fault=data.fault,budget=data.budget,status=REDUCTION_STATUSES[0],target=target,input_snapshot={'entries':entries,'config':cfg,'fault':data.fault},search_state={'tested':{},'best_indices':list(range(len(entries))),'state':{'stage':'search'}})
    db.add(x);db.commit();queue.rpush('lsm:reductions',x.id);return serialize(x)
def replay(db,ident):
    """Replay the current shortest sample (or the full batch before any) and
    report the stage, key, expected and actual value of its first divergence."""
    x=db.get(Reduction,ident)
    if not x:raise HTTPException(404,'缩减任务不存在')
    entries=x.input_snapshot['entries'];config=x.input_snapshot['config'];fault=x.input_snapshot['fault']
    result=x.result or {}
    sample_entries=result.get('sample') or entries or []
    run=simulate(sample_entries,config,fault)
    return {'id':x.id,'sample_size':len(sample_entries),'original_size':len(entries),'first_divergence':run.get('first_divergence'),'target':x.target,'matches_target':run.get('first_divergence')==x.target}
def extend(db,ident,amount):
    x=db.get(Reduction,ident)
    if not x:raise HTTPException(404,'缩减任务不存在')
    if x.status=='done':raise HTTPException(409,'该缩减已证明最短，无需增加额度')
    if x.status=='running':raise HTTPException(409,'该缩减正在后台执行，请稍后再追加额度')
    x.budget=x.budget+amount
    if x.status=='exhausted':x.status='queued';queue.rpush('lsm:reductions',x.id)
    db.commit();return serialize(x)
