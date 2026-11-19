"""Deterministic educational LSM model. MySQL persists metadata; this is not its engine."""
import hashlib,json

# Simulated faults used by the reduction workshop. They are injected into the
# teaching model only; a normal trial (fault=None) keeps the strict oracle check.
from ..constants.enums import FAULTS,FAILURE_PHASES as PHASES

def simulate(entries,config,fault=None):
    if fault is not None and fault not in FAULTS:raise ValueError('未知的模拟故障')
    if not 1<=len(entries)<=2000:raise ValueError('操作数必须在1到2000之间')
    capacity=config['memtable_limit'];trigger=config['l0_trigger'];depth=config['max_levels']
    if not 2<=capacity<=64 or not 2<=trigger<=8 or not 2<=depth<=6:raise ValueError('层级配置超出允许范围')
    levels=[[] for _ in range(depth)];mem={};oracle={};timeline=[];writes=0;flushes=0;compactions=0
    def merged(tables,inject=True):
        latest={}
        stale=inject and fault=='keep_stale_version_in_tiered'
        for table in tables:
            for k,v in table.items():
                if k not in latest:latest[k]=v
                elif stale:
                    if v['seq']<latest[k]['seq']:latest[k]=v
                elif latest[k]['seq']<v['seq']:latest[k]=v
        if inject and fault=='drop_tombstones_in_tiered':
            latest={k:v for k,v in latest.items() if not v['deleted']}
        return dict(sorted(latest.items()))
    def snapshot():return [{'level':i,'tables':[{'entries':len(t),'min_key':min(t) if t else None,'max_key':max(t) if t else None,'tombstones':sum(v['deleted'] for v in t.values())} for t in tables]} for i,tables in enumerate(levels)]
    def record(event,level,rows):timeline.append({'step':len(timeline)+1,'event':event,'level':level,'output_entries':rows,'table_counts':[len(t) for t in levels]})
    def cascade(i):
        nonlocal writes,compactions
        if len(levels[i])<trigger:return
        table=merged(levels[i]);levels[i]=[];target=min(i+1,depth-1)
        levels[target].append(table);writes+=len(table);compactions+=1;record('tiered_compaction_keep_tombstones',target,len(table))
        if target!=i:cascade(target)
    def flush():
        nonlocal writes,flushes
        if not mem:return
        table=dict(sorted(mem.items()));mem.clear();levels[0].append(table);writes+=len(table);flushes+=1;record('memtable_flush',0,len(table));cascade(0)
    for seq,e in enumerate(entries,1):
        key=e['key'];deleted=e['op']=='delete'
        if e['op'] not in ('put','delete') or not key or len(key)>64:raise ValueError('操作或键不合法')
        if not deleted and (not isinstance(e.get('value'),str) or len(e['value'])>200):raise ValueError('put必须包含不超过200字的字符串')
        mem[key]={'seq':seq,'value':None if deleted else e['value'],'deleted':deleted}
        if deleted:oracle.pop(key,None)
        else:oracle[key]=e['value']
        if len(mem)>=capacity:flush()
    flush()
    universe=sorted({e['key'] for e in entries}|{'__missing_probe__'})
    def read_probe():
        found={};touches=0;oldest=fault=='read_oldest_version'
        for key in universe:
            best=None
            for tables in levels:
                for table in tables:
                    # No bloom-filter model; a min/max range match incurs one SSTable read.
                    if table and min(table)<=key<=max(table):
                        touches+=1
                        row=table.get(key)
                        if row and (best is None or (row['seq']<best['seq'] if oldest else row['seq']>best['seq'])):best=row
            if best and not best['deleted']:found[key]=best['value']
        return found,round(touches/len(universe),4),touches
    before_shape=snapshot();before_result,read_before,touches_before=read_probe();writes_before=writes
    tombstones_removed=0
    if config.get('final_compaction',True):
        # All levels participate: only here is it safe to drop deleted keys.
        complete=merged([table for tables in levels for table in tables],inject=False)
        tombstones_removed=sum(v['deleted'] for v in complete.values())
        table={k:v for k,v in complete.items() if not v['deleted']}
        if fault=='drop_latest_in_final_compaction' and table:
            # Only corrupts the final full-history output: discards the newest
            # surviving write, so the divergence appears after this step only.
            table.pop(max(table,key=lambda k:table[k]['seq']))
        levels[:]=[[] for _ in range(depth)]
        if table:levels[-1]=[table]
        writes+=len(table);compactions+=1;record('full_history_compaction_drop_tombstones',depth-1,len(table))
    actual,read_after,touches_after=read_probe()
    expected=dict(sorted(oracle.items()));actual=dict(sorted(actual.items()))
    def divergence(phase,result):
        for key in universe:
            if result.get(key)!=expected.get(key):return {'phase':phase,'key':key,'expected':expected.get(key),'actual':result.get(key)}
        return None
    first=divergence(PHASES[0],before_result) or divergence(PHASES[1],actual)
    if fault is None and (actual!=expected or before_result!=expected):raise ValueError('LSM结果与最后写入oracle不一致')
    checksum=lambda x:hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    result={'verified':True if fault is None else (first is None and actual==expected),'model':'教学 LSM 模型：Python内存算法；MySQL只保存业务输入与结果','operation_count':len(entries),'unique_input_keys':len({e['key'] for e in entries}),'live_keys':len(actual),'flushes':flushes,'compactions':compactions,'physical_entry_writes':writes,'write_amplification':round(writes/len(entries),4),'writes_before_final':writes_before,'read_amplification_before':read_before,'read_amplification_after':read_after,'probe_count':len(universe),'table_reads_before':touches_before,'table_reads_after':touches_after,'tombstones_removed':tombstones_removed,'before_levels':before_shape,'after_levels':snapshot(),'timeline':timeline,'actual':actual,'oracle':expected,'actual_checksum':checksum(actual),'oracle_checksum':checksum(expected),'policy':'层级合并永远保留墓碑；仅覆盖所有层级的最终合并允许清理墓碑。读放大=固定点查集合的平均范围命中SSTable数，写放大=实际写出条目数/用户操作数。'}
    if fault is not None:
        result['fault']=fault;result['first_divergence']=first
        result['divergence_count']=sum(1 for k in universe if before_result.get(k)!=expected.get(k))+sum(1 for k in universe if actual.get(k)!=expected.get(k))
    return result
