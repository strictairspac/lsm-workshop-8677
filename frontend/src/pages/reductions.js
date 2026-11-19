import{datasets}from'../stores/dataset.js';import{configs}from'../stores/config.js';import{reductions}from'../stores/reduction.js';import{create,extend,replay,download}from'../api/reduction.js';import{header}from'../components/common/header.js';import{table}from'../components/common/table.js';import{reductionBadge}from'../components/common/badge.js';import{esc,json}from'../utils/html.js';import{submit,notify}from'../hooks/feedback.js';import{session}from'../stores/session.js';import{FAULTS,PHASES}from'../constants/enums.js';
const STAGES={search:'收缩候选',proof:'证明最短',done:'已完成'};
const phase=p=>PHASES[p]||p||'—';
const val=v=>v===undefined||v===null?'（无此键）':JSON.stringify(v);
export function divergenceTable(d){return d?table(['阶段','键','期望值','实读值'],[[esc(phase(d.phase)),esc(d.key),esc(val(d.expected)),esc(val(d.actual))]]):'<p class="helper">尚未产生读错。</p>'}
export async function reductionsPage(el){
  const ds=await datasets.load();const cs=await configs.load();const rs=await reductions.load();
  const selected=Number(location.hash.split('/')[1]);
  const chosen=rs.find(x=>x.id===selected)||null;
  const writable=session.get().role!=='viewer';
  el.innerHTML=header('05','把读错缩到最短的那几笔','选择批次、配置与模拟故障，找出仍能重现首处读错的最短操作子序列。重放时阶段、键、期望值与实读值都须一致。')
  +`<div class="split"><section class="panel"><h2>缩减任务</h2><div class="actions" style="margin:0 0 20px"><button id="refresh">刷新</button><span class="muted">${rs.length} 个任务</span></div>${table(['任务','故障','状态','最短样本'],rs.map(x=>[`<a href="#reductions/${x.id}">${esc(x.name)}</a><br><small>#${x.id} / 批次#${x.dataset_id} · 配置#${x.config_id}</small>`,esc(FAULTS[x.fault]||x.fault),reductionBadge(x.status),x.result?`${x.result.sample_size} / ${x.result.original_size} 笔${x.result.proven_shortest?' · 已证最短':''}`:'—']))}
  <h2 style="margin-top:30px">诊断面板</h2>${chosen?renderDetail(chosen,cs,ds,writable):'<p class="helper">在上方选择一个缩减任务，或先在右侧发起。</p>'}
  </section><aside class="panel"><h2>${writable?'发起缩减':'只读'}</h2>${writable?`<form id="reduction-form"><label>任务名称</label><input name="name" value="reduce-${Date.now().toString().slice(-6)}" required maxlength="120"><label>键值写入批次</label><select name="dataset_id">${ds.map(x=>`<option value="${x.id}">${esc(x.name)} / ${x.operation_count}条</option>`).join('')}</select><label>存储配置</label><select name="config_id">${cs.map(x=>`<option value="${x.id}">${esc(x.name)}</option>`).join('')}</select><label>模拟故障</label><select name="fault">${Object.entries(FAULTS).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select><label>重放次数上限</label><input type="number" name="budget" min="1" max="200000" value="2000"><div class="actions"><button class="primary" type="submit">发起缩减 →</button></div></form><p class="helper">额度用完会保留当前样本并停止；追加额度后从中断处继续，已测候选不重复扣次数。原合并试验不受影响。</p>`:''}</aside></div>`;
  el.querySelector('#refresh').onclick=()=>reductionsPage(el);
  const form=el.querySelector('#reduction-form');
  if(form)form.onsubmit=e=>{e.preventDefault();submit(e.target,async()=>{const d=Object.fromEntries(new FormData(e.target));for(const k of ['dataset_id','config_id','budget'])d[k]=Number(d[k]);const x=await create(d);notify('缩减任务已提交');location.hash='reductions/'+x.id;await reductionsPage(el)})};
  const b=el.querySelectorAll('[data-act]');b.forEach(btn=>btn.onclick=async()=>{try{const id=Number(btn.dataset.id);if(btn.dataset.act==='extend'){const amount=Number(el.querySelector('#extend-amount')?.value||1000);await extend(id,amount);notify('已追加额度 '+amount)}else if(btn.dataset.act==='replay'){const r=await replay(id);notify(r.matches_target?'重放一致：首处读错与目标相同':'重放首处读错与目标不同')}else if(btn.dataset.act==='download'){await download(id)}await reductionsPage(el)}catch(e){notify(e.message)}});
}
function renderDetail(x,cs,ds,writable){
  const r=x.result||{};const info=table(['项目','值'],[['任务','#'+x.id+' '+esc(x.name)],['故障',esc(FAULTS[x.fault]||x.fault)],['批次','#'+x.dataset_id+' '+esc(ds.find(d=>d.id===x.dataset_id)?.name||'')],['配置','#'+x.config_id+' '+esc(cs.find(c=>c.id===x.config_id)?.name||'')],['原操作 / 当前样本',`${r.original_size??x.original_size??'—'} / ${r.sample_size??'—'}`],['重放次数',`${r.replays_used??0} / ${x.budget}`],['最短已证',r.proven_shortest?'是':'否'+(r.exhausted?'（额度用完）':'')],['当前阶段',r.status==='done'?'已结束':STAGES[r.stage]||'—']]);
  const target=divergenceTable(x.target);
  const sample=r.sample?`<h3>当前复现样本 · ${r.sample_size} 笔</h3><pre>${json(r.sample)}</pre>`:'<p class="helper">尚无样本，等待 worker。</p>';
  const replayed=r.first_divergence_after_replay!==undefined?`<h3>重放样本首处读错</h3>${divergenceTable(r.first_divergence_after_replay)}<p class="helper">与目标一致：${r.replay_matches_target?'是':'否'}</p>`:'';
  return `${info}${x.status==='exhausted'?`<p class="modelnote">${esc(r.note||'额度用完，样本已保存。')}</p>`:''}<h3>原始批次首处读错（目标）</h3>${target}<div class="actions"><button data-act="replay" data-id="${x.id}">重放当前样本 ↻</button>${writable?`<input id="extend-amount" type="number" min="1" value="1000" style="width:120px"><button data-act="extend" data-id="${x.id}" ${x.status==='done'?'disabled':''}>追加重放额度</button>`:''}<button data-act="download" data-id="${x.id}">下载 JSON ↓</button></div>${sample}${replayed}`;
}
