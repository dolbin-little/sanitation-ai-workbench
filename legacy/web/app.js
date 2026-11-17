'use strict';
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clock = n => `${String(Math.floor(n / 60)).padStart(2,'0')}:${String(Math.floor(n % 60)).padStart(2,'0')}`;
const kinds = {collection:'压缩收运车',hook:'勾臂运输车',sweeper:'道路洗扫车'};
const taskKinds = {collection:'点位收运',hook:'箱体转运',sweeper:'道路洗扫'};
const strategies = {halns:'H-ALNS风险调度',game:'安全任务博弈',reroute:'保持顺序绕行',adaptive:'动态插入优化',nearest:'最近车辆优先',fixed:'固定顺序均衡'};
const icons = {
 grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
 truck:'<path d="M2 5h12v12H2zm12 5h4l4 4v3h-8"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>',
 task:'<rect x="5" y="4" width="15" height="17" rx="2"/><path d="M9 3h7v4H9zm0 9h7m-7 4h7"/>',
 chart:'<path d="M3 3v18h18M7 16v-4m5 4V6m5 10V9"/>',
 clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/>',
 route:'<circle cx="5" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><path d="M5 7v8a4 4 0 004 4h8M7 5h8a4 4 0 014 4v3m-3-3 3 3 3-3"/>',
 pulse:'<path d="M2 12h5l3-8 4 16 3-8h5"/>',
 plus:'<path d="M12 5v14M5 12h14"/>',
 play:'<path d="m8 5 11 7-11 7z"/>',
 down:'<path d="M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5"/>',
 check:'<path d="m5 12 4 4L19 6"/>',
 shield:'<path d="M12 2 3 6v7c0 5 9 9 9 9s9-4 9-9V6z"/><path d="m8 12 3 3 5-6"/>',
 alert:'<path d="m12 3 10 18H2zM12 9v5m0 3v.1"/>',
 file:'<path d="M5 3h9l5 5v13H5zm9 0v6h5M8 13h8m-8 4h6"/>',
 settings:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>'
};
const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${icons[name]||icons.grid}</svg>`;
let state, page='dashboard', selected='V01', busy=false, auto=null, zoom=1, benchmark=null, search='', filter='all', vehicleFilter='all';
let toastTimer;
function toast(message,error=false){clearTimeout(toastTimer);$('#toast').textContent=message;$('#toast').className='show'+(error?' error':'');toastTimer=setTimeout(()=>$('#toast').className='',5000);}
async function request(action,body={}){
 const response=await fetch('/api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const result=await response.json();if(!response.ok)throw new Error(result.error||'请求失败');return result;
}
async function act(action,body={}){
 if(busy)return;busy=true;render();
 try{const r=await request(action,body);if(action==='benchmark')benchmark=r;else state=r;if(action==='advance'&&state.tasks.every(t=>t.status==='done')&&state.vehicles.every(v=>!v.active)&&Object.values(state.plan?.routes||{}).every(x=>!x.length))stopAuto();toast({plan:'候选方案已生成，请检查后确认',accept:'计划已下发至模拟车队',reject:'已保留当前执行计划',event:'事件已记录，请检查自动候选或手动求解',manual:'人工改派候选已生成，请到工作台确认',lock:'车辆锁定已更新',reset:'已恢复演示场景',import:'场景导入成功',benchmark:'对照实验已完成'}[action]||'状态已更新');}
 catch(e){stopAuto();toast(e.message,true);}finally{busy=false;render();}
}
function stopAuto(){clearInterval(auto);auto=null;}
// Compare remaining work, not the historical metrics saved when a plan was accepted.
function buildPlanPreview(snapshot,plan=snapshot.draft){
 const tasks=new Map(snapshot.tasks.map(t=>[t.id,t]));
 const active=new Map(snapshot.vehicles.filter(v=>v.active).map(v=>[v.id,v.active]));
 function index(p){
  const rows=new Map(), routes=new Map();
  for(const vid of new Set([...Object.keys(p?.routes||{}),...active.keys()])){
   const running=active.get(vid);
   const seq=[...(running?[running]:[]),...(p?.routes?.[vid]||[]).filter(a=>!running||a.task!==running.task||!a.task)];
   const remaining=seq.filter(a=>!a.task||tasks.get(a.task)?.status!=='done');
   let order=0;
   for(const step of remaining)if(step.task)rows.set(step.task,{vehicle:vid,order:++order,step,active:step===running});
   if(remaining.length)routes.set(vid,remaining);
  }
  return {rows,routes};
 }
 const before=index(snapshot.plan), after=index(plan);
 const frozen=new Set(plan?.frozen||[]), deferred=new Set(plan?.deferred||[]);
 const failures=new Map((plan?.unassigned||[]).map(u=>[u.id,u.reason]));
 const counts={added:0,reassigned:0,reordered:0,retimed:0,rerouted:0,removed:0};
 const changes=[];
 for(const task of snapshot.tasks){
  if(task.status==='done')continue;
  const old=before.rows.get(task.id), next=after.rows.get(task.id), tags=[];
  let timing=0;
  if(!old&&next){tags.push('新分配');counts.added++;}
  if(old&&next){
   if(old.vehicle!==next.vehicle){tags.push('车辆改派');counts.reassigned++;}
   else if(old.order!==next.order){tags.push('顺序调整');counts.reordered++;}
   timing=Math.floor(next.step.finish)-Math.floor(old.step.finish);
   if(timing){tags.push('时间变化');counts.retimed++;}
   if(JSON.stringify([old.step.path,old.step.service_path])!==JSON.stringify([next.step.path,next.step.service_path])){tags.push('路线变化');counts.rerouted++;}
  }
  if(old&&!next){tags.push(deferred.has(task.id)?'窗口外暂缓':'未排入候选');counts.removed++;}
  if(!old&&!next){if(failures.has(task.id))tags.push('待人工处理');else if(deferred.has(task.id))tags.push('窗口外暂缓');}
  if(tags.length)changes.push({task,old,next,tags,timing,frozen:frozen.has(task.id),reason:failures.get(task.id)});
 }
 const facilities=seq=>seq.filter(a=>a.kind==='facility').map(a=>`${a.facility||a.start}:${a.label}`);
 const facilityOrder=seq=>seq.filter(a=>a.task||a.kind==='facility').map(a=>a.task||`facility:${a.facility||a.start}`);
 const routeChanges=[];
 for(const vid of new Set([...before.routes.keys(),...after.routes.keys()])){
  const old=before.routes.get(vid)||[], next=after.routes.get(vid)||[];
  const oldFacilities=facilities(old), newFacilities=facilities(next);
  const facilityChanged=JSON.stringify(oldFacilities)!==JSON.stringify(newFacilities)||
   ((oldFacilities.length||newFacilities.length)&&JSON.stringify(facilityOrder(old))!==JSON.stringify(facilityOrder(next)));
  const other=seq=>seq.filter(a=>!a.task).map(a=>[a.kind,a.path,a.service_path,Math.floor(a.finish)]);
  if(facilityChanged||JSON.stringify(other(old))!==JSON.stringify(other(next)))routeChanges.push({vehicle:vid,old,next,facilityChanged,oldFacilities,newFacilities});
 }
 return {changes,counts,routeChanges,routes:after.routes,before:before.rows,after:after.rows,frozen};
}
const previewClock=n=>Number.isFinite(n)?clock(n):'—';
function previewVehicle(id){const v=state.vehicles.find(v=>v.id===id);return v?`${v.name}（${id}）`:id;}
function previewAssignment(row){return row?`${esc(previewVehicle(row.vehicle))} · 第 ${row.order} 项 · ${previewClock(row.step.finish)} 完成`:'未分配';}
function previewChanges(view){
 const items=view.changes.map(c=>`<article class="plan-change-item"><div class="plan-change-title"><button class="text" data-action="task-detail" data-task="${esc(c.task.id)}">${esc(c.task.id)} · ${esc(c.task.name)}</button><span class="plan-change-tags">${c.tags.map(t=>`<span>${t}</span>`).join('')}${c.frozen?'<span class="frozen">冻结保留</span>':''}</span></div><div class="plan-before"><span>原方案</span>${previewAssignment(c.old)}</div><div class="plan-after"><span>候选方案</span>${c.next?previewAssignment(c.next):esc(c.reason||(c.tags.includes('窗口外暂缓')?'超出本次滚动窗口，暂缓安排':'本次未排入，需人工检查'))}</div>${c.timing?`<p class="plan-change-note">预计完成${c.timing<0?'提前':'延后'} ${Math.abs(c.timing)} 分钟${c.next?.step.late>0?`，逾期 ${Math.ceil(c.next.step.late)} 分钟`:''}</p>`:''}${c.tags.includes('路线变化')?'<p class="plan-change-note">通行路线或作业方向有变化，可点击下方“地图查看”核对。</p>':''}${c.next?`<button class="text small" data-action="select-vehicle" data-vehicle="${esc(c.next.vehicle)}">地图查看 ${esc(c.next.vehicle)} →</button>`:''}</article>`).join('');
 const routeItems=view.routeChanges.map(c=>`<article class="plan-change-item"><strong>${esc(previewVehicle(c.vehicle))} · ${c.facilityChanged?'补给安排调整':'补给／返回行程调整'}</strong>${c.facilityChanged?`<p class="plan-before">原补给：${esc(c.oldFacilities.map(x=>x.slice(x.indexOf(':')+1)).join(' → ')||'无')}</p><p class="plan-after">候选补给：${esc(c.newFacilities.map(x=>x.slice(x.indexOf(':')+1)).join(' → ')||'无')}<br>具体插入位置见下方车辆行程。</p>`:`<p class="plan-change-note">原行程结束 ${previewClock(c.old.at(-1)?.finish)}，候选行程结束 ${previewClock(c.next.at(-1)?.finish)}；具体路线见下方车辆行程。</p>`}</article>`).join('');
 return items+routeItems||'<p class="plan-preview-empty">本次候选与当前剩余计划的任务、顺序、预计时间和路线一致。可在下方核对保留安排。</p>';
}
function previewItinerary(view){
 return [...view.routes].map(([vid,seq])=>`<details class="plan-vehicle" open><summary>${esc(previewVehicle(vid))}<span>${seq.filter(a=>a.task).length} 项任务 · ${seq.filter(a=>a.kind==='facility').length} 次补给</span></summary><ol>${seq.map(a=>{const task=state.tasks.find(t=>t.id===a.task);return `<li><div class="plan-step-title">${a.task?`${esc(a.task)} · ${esc(task?.name||a.label)}`:esc(a.label||'返回车场')}${a.task&&view.frozen.has(a.task)?'<span class="label gray">冻结</span>':''}</div><div>${previewClock(a.begin??a.arrive)}—${previewClock(a.finish)}${a===state.vehicles.find(v=>v.id===vid)?.active?' · 执行中保留':''}${a.task?` · 截止 ${previewClock(a.deadline??task?.deadline)}`:''}${a.late>0?` · <span class="plan-late">预计逾期 ${Math.ceil(a.late)} 分钟</span>`:''}</div><div class="plan-step-place">${esc(a.source??a.start)} → ${esc(a.start)}${a.start!==a.end?` → ${esc(a.end)}`:''}</div></li>`;}).join('')}</ol><button class="text small" data-action="select-vehicle" data-vehicle="${esc(vid)}">地图查看 ${esc(vid)} →</button></details>`).join('')||'<p class="plan-preview-empty">候选方案没有可执行行程，请核对待人工处理和暂缓任务。</p>';
}
function planPreview(){
 if(!state.draft)return '';
 const view=buildPlanPreview(state), c=view.counts;
 const summary=[['新分配',c.added],['车辆改派',c.reassigned],['顺序调整',c.reordered],['时间变化',c.retimed],['路线变化',c.rerouted],['未排入',c.removed]].filter(x=>x[1]);
 return `<section class="plan-preview" aria-label="候选方案具体安排"><h3>本次方案具体改动</h3><p class="plan-preview-help">${state.plan?'与当前已确认的剩余计划比较':'首次生成方案，以下为新任务安排'} · 尚未下发</p><div class="plan-change-counts">${summary.map(([label,n])=>`<span>${label} <b>${n}</b></span>`).join('')||'<span>任务安排保持不变</span>'}${view.routeChanges.length?`<span>补给／返回调整 <b>${view.routeChanges.length} 辆</b></span>`:''}</div><div class="plan-change-list" tabindex="0" aria-label="具体方案变更列表">${previewChanges(view)}</div><details class="plan-itinerary" open><summary>候选车辆完整行程（${view.routes.size} 辆）</summary><p class="plan-preview-help">含保留任务、补给和返回安排；预计时间按分钟显示。</p><div class="plan-itinerary-list" tabindex="0" aria-label="候选车辆任务和补给顺序">${previewItinerary(view)}</div></details><button class="text" data-action="candidate-tasks">在任务中心查看候选任务 →</button></section>`;
}
function assignments(plan=state.draft||state.plan){const out={};for(const [v,seq] of Object.entries(plan?.routes||{}))for(const a of seq)if(a.task)out[a.task]={vehicle:v,step:a};for(const v of state.vehicles)if(v.active?.task)out[v.active.task]={vehicle:v.id,step:v.active};return out;}
function title(){return {research:['算法研究中心','预测、风险优化、分级恢复与安全验收。'],dashboard:['调度工作台','掌握车队运行状态，让每一次调度有据可依。'],tasks:['任务中心','查看点位收运与道路作业，锁定任务或人工改派。'],fleet:['车辆资源','异构车队、运行状态与资源余量一览。'],experiments:['算法实验室','在相同快照与约束下，比较四种调度策略。'],logs:['运行记录','每一次事件、计划确认与仿真操作，均可追溯。'],data:['数据与说明','导入业务样例，了解第一版的能力和适用边界。']}[page];}
function nav(id,label,ico,count){return `<button class="navitem ${page===id?'active':''}" data-nav="${id}">${icon(ico)}<span>${label}</span>${count!==undefined?`<small class="navcount">${count}</small>`:''}</button>`;}
function render(){
 if(!state)return;
 const [name,desc]=title();
 $('#app').innerHTML=`${busy?'<div class="busyline"></div>':''}<aside class="sidebar"><div class="brand"><div class="brandmark">${icon('route')}</div><div><b>环卫智枢</b><small>URBAN DISPATCH</small></div></div><div class="navlabel">运行管理 / OPERATIONS</div><a href="/" style="display:block;margin:12px 20px;color:#8bd0bd">↗ 环卫驾驶协同</a><nav>${nav('dashboard','调度工作台','grid')}${nav('tasks','任务中心','task',state.tasks.length)}${nav('fleet','车辆资源','truck',state.vehicles.length)}${nav('experiments','算法实验室','chart')}${nav('research','算法研究中心','shield')}${nav('logs','运行记录','file')}</nav><div class="navlabel">工作空间 / WORKSPACE</div>${nav('data','数据与说明','settings')}<div class="sidebottom"><div class="env"><strong><i class="dot"></i>本地演示环境</strong>合成业务数据 · SQLite 持久化<br>版本 0.2 / 算法研究版</div><div class="profile"><div class="avatar">调</div><div>调度员工作空间<small>本地单用户 · 人工确认</small></div></div></div></aside><main class="main"><header class="topbar"><div class="crumb">城市运行管理 <span> / </span><b>${name}</b></div><div class="topright"><span class="quiet">${esc(state.name)}</span><span class="mode"><i class="dot"></i>仿真模式</span><span>${icon('clock')} ${clock(state.now)}</span></div></header><div class="content"><div class="heading"><div><div class="eyebrow">SANITATION INTELLIGENCE / 01</div><h1>${name}</h1><p class="sub">${desc}</p></div><div class="actions">${page==='dashboard'?`<button data-action="event-dialog">${icon('plus')}注入事件</button><button class="primary" data-action="plan">${icon('route')}${state.plan?'生成重调度方案':'生成初始计划'}</button>`:page==='experiments'?`<button class="primary" data-action="benchmark">${icon('play')}运行对照实验</button>`:`<button data-action="export">${icon('down')}导出运行快照</button>`}</div></div>${state.needs_replan?'<div class="banner">'+icon('alert')+'业务约束已变化。请检查并确认调度候选后继续仿真；当前计划仅供对照。</div>':''}${({dashboard:dashboard,tasks:taskPage,fleet:fleetPage,experiments:experimentPage,logs:logsPage,data:dataPage,research:researchPage}[page])()}<footer class="pagefoot"><span>环卫智枢 · 让资源协同，让城市更洁净</span><span>合成路网 / 无真实车辆连接 · 状态版本 r${state.revision}</span></footer></div></main>`;
 if(busy)document.querySelectorAll('#app button').forEach(b=>b.disabled=true);
 if(page==='dashboard')renderMap();
}
function stat(label,value,unit,foot,ico,color=''){return `<div class="stat ${color}"><span class="stat-label">${label}</span><span class="stat-icon">${icon(ico)}</span><div class="stat-value">${value}<small>${unit}</small></div><div class="stat-foot">${foot}</div></div>`;}
function dashboard(){
 const done=state.tasks.filter(t=>t.status==='done'), running=state.vehicles.filter(v=>v.active).length;
 const late=state.tasks.filter(t=>t.status!=='done'&&t.deadline<state.now).length;
 const km=state.vehicles.reduce((a,v)=>a+v.km,0).toFixed(1);
 return `<section class="stats">${stat('可用车辆',state.vehicles.filter(v=>v.enabled).length,`/ ${state.vehicles.length} 辆`,`${running} 辆执行中 · ${state.vehicles.filter(v=>!v.enabled).length} 辆故障`,'truck')}${stat('已完成任务',done.length,`/ ${state.tasks.length} 项`,`完成进度 ${Math.round(done.length/state.tasks.length*100)}% · ${state.tasks.filter(t=>t.status==='running').length} 项进行中`,'task','blue')}${stat('当前逾期待办',late,'项','按当前仿真时刻统计，区别于预测逾期','clock','orange')}${stat('已记账运行里程',km,'km','完成动作累计 · 含作业行驶','route','purple')}</section><section class="workgrid"><div><div class="card"><div class="cardhead"><div><h2>片区运行态势</h2><p class="sub">车辆位置 · 作业任务 · 设施与路线</p></div><select id="routeSelect" aria-label="选择显示路线"><option value="all" ${selected==='all'?'selected':''}>全部车辆路线</option>${state.vehicles.map(v=>`<option value="${esc(v.id)}" ${selected===v.id?'selected':''}>${esc(v.name)} · ${kinds[v.kind]}</option>`).join('')}</select></div><div class="map-wrap"><div id="map"></div><div class="map-status"><i class="dot"></i>${state.draft?'候选方案预览':state.plan?'已确认执行计划':'等待生成计划'}</div><div class="map-control"><button data-action="zoom-in" aria-label="放大地图">+</button><button data-action="zoom-out" aria-label="缩小地图">−</button><button data-action="zoom-reset" aria-label="复位地图">⌾</button></div><span class="map-note">离线合成路网 · 非真实地理底图</span></div><div class="maplegend"><div class="legenditems"><span><i class="legenddot" style="background:#209e81"></i>待执行</span><span><i class="legenddot" style="background:#df9c42"></i>高优先级</span><span><i class="legenddot" style="background:#b3c4c0"></i>已完成</span><span>◆ 综合补给站</span></div><span>道路通行 + 服务单元</span></div><div class="timelinebar"><button class="small" data-action="auto" ${!state.plan||state.needs_replan?'disabled':''}>${icon('play')}${auto?'暂停':'自动演示'}</button><div class="clock">${clock(state.now)}<small>模拟时钟</small></div><div class="track"><span style="width:${(state.now-420)/600*100}%"></span></div><button class="small" data-action="advance" ${!state.plan||state.needs_replan?'disabled':''}>+10 分钟</button></div>${routeDetails()}</div><div class="card lower"><div class="cardhead"><h2>任务执行概览</h2><button class="text" data-nav="tasks">查看全部 →</button></div>${taskTable(state.tasks.filter(t=>t.status!=='done').sort((a,b)=>b.priority-a.priority||a.deadline-b.deadline).slice(0,5),true)}</div></div><div class="stack">${planPanel()}<div class="card"><div class="cardhead"><h2>事件动态</h2><span class="label orange">${state.events.length} 条</span></div><div class="panelbody">${state.events.length?state.events.slice(0,4).map(e=>`<div class="eventitem"><time class="eventtime">${clock(e.at)} · 模拟事件</time><div class="eventtitle"><i class="dot"></i><span>${esc(e.label)}</span></div></div>`).join(''):`<div class="empty">${icon('shield')}运行环境平稳<br>可注入满溢、投诉、故障与拥堵事件</div>`}</div></div></div></section>`;
}
function routeDetails(){
 const plan=state.draft||state.plan;if(!plan||selected==='all')return '';
 const v=state.vehicles.find(v=>v.id===selected);if(!v)return '';
 const seq=[...(v.active?[v.active]:[]),...(plan.routes[selected]||[])];
 return `<div class="route-details"><strong>${esc(v.name)} · ${kinds[v.kind]}</strong><p>${seq.length?`${seq.filter(a=>a.task).length} 项剩余任务 · ${seq.filter(a=>a.kind==='facility').length} 次补给 · 预计 ${clock(seq.at(-1).finish)} 返回车场`:'暂无剩余行程'}</p>${seq.slice(0,7).map(a=>`<span class="route-chip">${a.task?esc(a.task):a.kind==='facility'?'补给':'车场'} ${clock(a.finish)}</span>`).join('')}${seq.length>7?'<span class="sub">…</span>':''}</div>`;
}
function planPanel(){
 const p=state.draft||state.plan;
 if(!p)return `<div class="card"><div class="cardhead"><h2>调度方案</h2><span class="label gray">待计算</span></div><div class="panelbody"><div class="empty">${icon('route')}准备好，让车队有序出发<br>基于车型、容量、时间窗生成可执行路线</div><button class="primary" style="width:100%" data-action="plan">生成初始计划</button><p class="notice">算法生成建议，调度员确认后执行。无法分配的任务会显式列出。</p></div></div>`;
 const m=p.metrics;
 return `<div class="card"><div class="cardhead"><h2>${state.draft?'候选调度方案':'已确认方案'}</h2><span class="label ${state.draft?'orange':''}">${state.draft?'待人工确认':'执行中'}</span></div><div class="panelbody"><div class="planhero"><strong>${strategies[p.strategy]}</strong>${state.draft?'下方可直接核对任务、车辆和时间变化，确认后执行。':`于 ${clock(p.at)} 确认的规划快照；指标不随执行扣减。`}</div>${planPreview()}<div class="mini-grid"><div>规划非作业里程<b>${m.deadhead_km}<small class="sub"> km</small></b></div><div>规划逾期任务<b>${m.late_tasks}<small class="sub"> 项</small></b></div><div>规划覆盖任务<b>${m.scheduled}<small class="sub"> 项</small></b></div><div>计算耗时<b>${m.runtime_ms}<small class="sub"> ms</small></b></div></div><div class="pair"><span>车辆间改派 / 冻结任务</span><b>${m.changes} / ${p.frozen.length}</b></div>${p.version===2?`<p class="notice">安全盾：${p.shield?.passed?'通过':'拒绝'} · CVaR ${p.risk.cvar.toFixed(2)} · 窗口外暂缓 ${p.deferred.length} 项</p>`:''}<div class="pair"><span>待人工处理</span><button class="text" data-action="unassigned">${m.unassigned} 项 →</button></div><p class="notice">截止时间为软约束，逾期可排入但明确提示。容量、车型、设施开放与班次为硬约束。</p>${state.draft?'<div class="actions"><button class="primary" data-action="accept">'+icon('check')+'确认下发</button><button data-action="reject">拒绝</button><button class="text" data-action="changes">展开全部改动</button></div>':'<button class="text" data-action="changes">查看方案改派记录 →</button>'}</div></div>`;
}
function taskTable(tasks,compact=false){
 const owners=assignments();
 return `<div class="tablewrap"><table><thead><tr><th>任务 / 服务单元</th><th>状态</th><th>截止时间</th><th>${state.draft?'候选执行车辆':'执行车辆'}</th>${compact?'':'<th>预测完成</th><th>操作</th>'}</tr></thead><tbody>${tasks.map(t=>{const a=owners[t.id], status={pending:'待执行',running:'执行中',done:'已完成'}[t.status];return `<tr><td class="taskname"><strong>${esc(t.name)}</strong><small>${esc(t.id)} · ${taskKinds[t.kind]} · 优先级 P${4-t.priority}</small></td><td><span class="status-dot ${t.status}"></span>${status}</td><td><span style="color:${t.status!=='done'&&t.deadline<state.now?'#c66b43':'inherit'}">${clock(t.deadline)}</span></td><td>${esc(t.completed_by||(a?.vehicle?(state.draft?'候选 ':'')+a.vehicle:'未分配'))}${t.locked_to?' 🔒':''}</td>${compact?'':`<td>${t.completed_at?clock(t.completed_at):a?clock(a.step.finish):'—'}${a?.step.late>0?'<span class="label orange">逾期</span>':''}</td><td><button class="text" data-task="${esc(t.id)}" data-action="task-detail">详情</button>${t.status==='pending'?`<button class="text" data-task="${esc(t.id)}" data-action="manual-dialog">改派</button><button class="text" data-task="${esc(t.id)}" data-action="lock">${t.locked_to?'解锁':'锁车'}</button>`:''}</td>`}</tr>`;}).join('')||`<tr><td colspan="6" class="empty">没有匹配的任务</td></tr>`}</tbody></table></div>`;
}
function filteredTasks(){
 const owners=assignments();
 return state.tasks.filter(t=>(filter==='all'||(filter==='candidate'?state.draft&&t.status!=='done'&&owners[t.id]:t.status===filter))&&(t.name.toLowerCase().includes(search.toLowerCase())||t.id.toLowerCase().includes(search.toLowerCase())));
}
function taskPage(){
 if(filter==='candidate'&&!state.draft)filter='all';
 const list=filteredTasks();
 const options=[['all','全部状态'],...(state.draft?[['candidate','本次候选安排']]:[]),['pending','待执行'],['running','执行中'],['done','已完成']];
 return `${state.draft?'<div class="banner candidate-notice">'+icon('route')+'正在预览候选方案：车辆与预计完成时间可在下表查看，确认下发后才执行。<button class="text" data-nav="dashboard">返回工作台核对 →</button></div>':''}<div class="card"><div class="toolbar"><input class="search" id="search" placeholder="搜索任务名称或编号…" aria-label="搜索任务" value="${esc(search)}"><select id="taskFilter" aria-label="任务状态">${options.map(([v,l])=>`<option value="${v}" ${v===filter?'selected':''}>${l}</option>`).join('')}</select><span class="count">${list.length} 项任务 · 锁车约束只固定车辆，冻结前缀还固定顺序</span></div><div id="task-results">${taskTable(list)}</div></div>`;
}
function fleetPage(){return `<div class="fleetgrid">${state.vehicles.map(v=>`<div class="card vehiclecard"><div class="vhead"><div class="vtitle">${icon('truck')}<div><strong>${esc(v.name)}</strong><small>${kinds[v.kind]} · ${esc(v.id)}</small></div></div><span class="label ${!v.enabled?'red':v.active?'':'gray'}">${!v.enabled?'故障停用':v.active?'执行中':'待命'}</span></div><div class="pair"><span>当前位置节点</span><b>${esc(v.node)}</b></div><div class="pair"><span>当班人员 / 剩余能源</span><b>${esc(v.crew||'未配置')} / ${v.energy_capacity?Number(v.energy??v.energy_capacity).toFixed(1):'未建模'}</b></div><div class="pair"><span>当前动作</span><b>${esc(v.active?.label||'暂无')}</b></div><div class="resource"><label>已完成收运载荷<span>${v.load.toFixed(1)} / ${v.capacity} t</span></label><div class="progress"><span style="width:${v.load/v.capacity*100}%"></span></div></div>${v.water_capacity?`<div class="resource"><label>水箱余量<span>${v.water.toFixed(1)} / ${v.water_capacity} m³</span></label><div class="progress"><span style="width:${v.water/v.water_capacity*100}%;background:#69a9ca"></span></div></div>`:'<div class="notice">本车型不消耗洗扫用水</div>'}<div class="vfoot"><span>已记账 ${v.km.toFixed(1)} km · ${clock(v.shift_end)} 下班</span><button class="text" data-action="select-vehicle" data-vehicle="${esc(v.id)}">查看路线 →</button></div></div>`).join('')}</div>`;}
function experimentPage(){
 const cols=[['scheduled','覆盖任务','项'],['unassigned','未分配','项'],['late_tasks','预测逾期','项'],['deadhead_km','规划非作业行驶','km'],['changes','车辆改派','次'],['runtime_ms','计算耗时','ms']];
 return `<div class="card lower"><div class="cardhead"><h2>公开基准实验</h2><a class="primary" href="/public-benchmarks/report.html" target="_blank" rel="noopener">查看全库实验报告 ↗</a></div><div class="intro"><p>Solomon / CARP / TDCARP 原始数据、配对随机种子、独立路线验算。报告显示实际进度、失败和未服务任务；原生子问题算法与下方平台快照实验分开统计。</p></div></div><div class="compare-note">固定顺序均衡、最近车辆优先、贪心插入与H-ALNS共用同一当前快照、车型/容量约束、冻结前缀和截止时间。结果为合成数据上的规划对照，不代表企业实际节省率。</div><div class="card"><div class="cardhead"><h2>策略对照</h2><span class="sub">${benchmark?`快照 ${clock(benchmark.at)} · r${benchmark.revision}${benchmark.revision!==state.revision?'（历史结果，当前状态已变化）':''}`:'等待运行'}</span></div>${benchmark?`<div class="tablewrap"><table><thead><tr><th>策略</th>${cols.map(c=>`<th>${c[1]}</th>`).join('')}</tr></thead><tbody>${benchmark.results.map(r=>`<tr><td><strong>${strategies[r.strategy]}</strong></td>${cols.map(c=>`<td>${r[c[0]]} ${c[2]}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:'<div class="empty">'+icon('chart')+'点击「运行对照实验」，在相同条件下计算结果。</div>'}</div>${benchmark?`<div class="benchmark">${barCard('规划非作业里程','deadhead_km','km')}${barCard('预测逾期任务','late_tasks','项')}</div>`:''}<div class="card lower"><div class="cardhead"><h2>算法边界与解释</h2><span class="codebadge">engine.py</span></div><div class="intro"><p>四种策略共用有向时变路网、指定作业弧、人员资质、多资源和设施泊位约束。H-ALNS采用自适应破坏—修复与局部强化，周期调用CP-SAT受限邻域修复；初始化和插入位置候选集有预算限制，不保证全局最优。</p><p>F1优先服务覆盖与期望迟到，F2评价五个压力情景下的CVaR，F3评价成本、能源代理和路线稳定。对照必须同时看覆盖、逾期和耗时，不能只报里程。</p><p>冻结前缀保留已承诺动作；任一新候选经独立安全盾检查。预测、搜索轨迹、参数与分级控制见「算法研究中心」。研究实验不是企业实测收益。</p></div></div>`;
}
function barCard(title,key,unit){const max=Math.max(1,...benchmark.results.map(r=>r[key]));return `<div class="card"><div class="cardhead"><h2>${title}</h2><span class="sub">越低越好，需结合服务覆盖率</span></div><div class="bars">${benchmark.results.map(r=>`<div class="barrow"><span>${strategies[r.strategy]}</span><div class="bar"><i style="width:${r[key]/max*100}%"></i></div><b>${r[key]} ${unit}</b></div>`).join('')}</div></div>`;}
function logsPage(){return `<div class="card"><div class="cardhead"><h2>操作与事件审计</h2><span class="sub">最近 ${state.audit.length} 条 · 本地持久化</span></div>${state.audit.map(a=>`<div class="logrow"><time>${clock(a.at)}</time><div>${esc(a.message)}<small>状态版本 r${a.revision}</small></div></div>`).join('')||'<div class="empty">暂无操作记录</div>'}</div>`;}
function dataPage(){return `<div class="card"><div class="cardhead"><h2>场景数据</h2><span class="label">本地存储</span></div><div class="intro"><p>当前场景：${esc(state.name)}。${state.vehicles.length} 辆车辆、${state.tasks.length} 项任务、${state.facilities.length} 处设施、${state.nodes.length} 个路网节点。</p><p>下载 JSON 模板后替换车辆、任务和路网字段。时间均为当日零点起分钟数；容量单位为吨，水量为立方米；路段距离单位为公里。导入开启新的演示日，将清空当前执行记录，请先导出快照。</p><div class="actions"><button data-action="template">下载场景模板</button><button data-action="import-dialog">导入 JSON 场景</button><button data-action="export">导出完整运行快照</button><button data-action="research-demo-dialog">载入完整研究场景</button><button class="danger" data-action="reset-dialog">重置基础演示数据</button></div><input id="fileInput" type="file" accept=".json,application/json" hidden><p class="help">运行快照用于归档，导入时只读取场景定义并重置执行状态，不恢复历史时间和已完成任务。</p></div></div><div class="card lower"><div class="cardhead"><h2>研究版功能与边界</h2></div><div class="intro"><p>车辆与任务管理、离线路网最短路、点/道路服务单元、补给和卸载、约束插入调度、局部改进、人工确认、人工改派、任务锁车、执行前缀冻结、离散时间仿真、事件注入、三策略对照、SQLite持久化、运行快照导入导出。</p><p>当前不接入真实 GPS、实时交通、司机端或企业平台；已增加预测训练、人员资格匹配、泊位预约和研究算法；未接入真实驾驶员回执或生产级多用户鉴权。强化学习按计划书列为后续方向。道路绘制位置为示意坐标，无法用于实车导航。</p><p>建议下一步：先访谈一个实际车队，取得脱敏任务、车辆、设施和历史轨迹，再校准作业时间与约束，用历史数据回放评价。</p></div></div>`;}

function renderMap(){
 const ns=state.nodes, minx=Math.min(...ns.map(n=>n.x)), maxx=Math.max(...ns.map(n=>n.x)), miny=Math.min(...ns.map(n=>n.y)), maxy=Math.max(...ns.map(n=>n.y));
 const xy=Object.fromEntries(ns.map(n=>[n.id,[65+(n.x-minx)/Math.max(1,maxx-minx)*750,50+(n.y-miny)/Math.max(1,maxy-miny)*380]]));
 const points=path=>path.map(n=>xy[n]?.join(',')||'').join(' ');
 let svg='<svg class="map" viewBox="0 0 880 480" role="img" aria-label="合成片区路网与车辆任务地图"><defs><pattern id="blocks" width="75" height="47.5" patternUnits="userSpaceOnUse"><rect x="11" y="10" width="22" height="15" rx="2" fill="#e0e7df"/><rect x="39" y="11" width="23" height="26" rx="2" fill="#e4e9e2"/></pattern><filter id="shadow"><feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity=".15"/></filter></defs><rect width="880" height="480" fill="#edf1e9"/>';
 svg+=`<g transform="translate(440 240) scale(${zoom}) translate(-440 -240)"><rect x="30" y="20" width="820" height="440" fill="url(#blocks)"/><path d="M320 30q100 70 60 180t90 240h130q-110-115-90-230T435 20z" fill="#d5e6e5"/><path d="M338 25q110 120 47 190t115 240" fill="none" stroke="#c0dad7" stroke-width="5"/><rect x="90" y="100" width="108" height="83" rx="18" fill="#d9e7d3"/><rect x="619" y="320" width="115" height="71" rx="18" fill="#d8e7d2"/>`;
 const seen=new Set();for(const e of state.edges){const key=[e.a,e.b].sort().join('|');if(seen.has(key))continue;seen.add(key);svg+=`<polyline points="${points([e.a,e.b])}" fill="none" stroke="#dbe2dc" stroke-width="10"/><polyline points="${points([e.a,e.b])}" fill="none" stroke="#fffef8" stroke-width="7"/>`;}
 svg+='<g fill="#9cafa7" font-size="11" font-family="Microsoft YaHei"><text x="94" y="139">社区作业片区</text><text x="646" y="348">公园绿地</text><text x="460" y="248" fill="#8eb1b2" transform="rotate(-65 460 248)">示意水域</text><text x="672" y="85">商业作业片区</text></g>';
 const p=state.draft||state.plan;
 if(p)for(const [vid,steps] of Object.entries(p.routes)){if(selected!=='all'&&selected!==vid)continue;const v=state.vehicles.find(v=>v.id===vid);for(const a of [...(v?.active?[v.active]:[]),...steps])svg+=`<polyline points="${points(a.path)}" fill="none" stroke="#0b9f82" stroke-width="${selected==='all'?1.8:3}" opacity="${selected==='all'?0.3:0.85}" stroke-linejoin="round"/><polyline points="${points(a.service_path)}" fill="none" stroke="#e0a043" stroke-width="5" opacity=".8"/>`;}
 for(const t of state.tasks){const [x,y]=xy[t.start];const color=t.status==='done'?'#b3c4c0':t.priority===3?'#df9c42':'#259b7e';svg+=`<circle class="task-dot" data-action="task-detail" data-task="${esc(t.id)}" cx="${x}" cy="${y}" r="${t.status==='done'?2.6:4}" fill="${color}" stroke="white" stroke-width="1.5"><title>${esc(t.id)} ${esc(t.name)}</title></circle>`;}
 for(const f of state.facilities){const [x,y]=xy[f.node];svg+=`<g transform="translate(${x} ${y})"><rect x="-9" y="-9" width="18" height="18" rx="4" fill="#476c7e" stroke="white" stroke-width="2"/><path d="M-4 0h8M0-4v8" stroke="white" stroke-width="1.5"/><text x="14" y="4" font-size="10" fill="#4b6c70" stroke="#fff" stroke-width="3" paint-order="stroke">${esc(f.name)}</text></g>`;}
 const homes=[...new Set(state.vehicles.map(v=>v.home))];for(const h of homes){const [x,y]=xy[h];svg+=`<g transform="translate(${x} ${y})"><rect x="-11" y="-11" width="22" height="22" rx="5" fill="#244852"/><text x="0" y="4" fill="white" font-size="12" text-anchor="middle">P</text><text x="16" y="20" font-size="11" fill="#406773">车场</text></g>`;}
 for(const [i,v] of state.vehicles.entries()){
   let pos=xy[v.node];const a=v.active;
   if(a){let path=a.path,fraction=(state.now-a.depart)/Math.max(.001,a.arrive-a.depart);if(state.now>=a.arrive){path=a.service_path;fraction=(state.now-a.begin)/Math.max(.001,a.finish-a.begin);}fraction=Math.min(1,Math.max(0,fraction));const p=fraction*(path.length-1),j=Math.floor(p),p0=xy[path[j]],p1=xy[path[Math.min(j+1,path.length-1)]];pos=[p0[0]+(p1[0]-p0[0])*(p-j),p0[1]+(p1[1]-p0[1])*(p-j)];}
   if(selected!=='all'&&selected!==v.id)continue;
   const offset=!v.active&&selected==='all'?(i%6)*5:0;
   svg+=`<g class="vehicle-pin" data-action="select-vehicle" data-vehicle="${esc(v.id)}" transform="translate(${pos[0]+offset} ${pos[1]})" filter="url(#shadow)"><circle r="14" fill="${v.enabled?'#028a74':'#c56d56'}" stroke="white" stroke-width="3"/><path d="M-7-5h8v8h-8zM1-2h4l3 3v2H1M-4 5h.1M5 5h.1" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round"/><text x="0" y="-23" text-anchor="middle" font-size="11" fill="#244c46" stroke="white" stroke-width="3" paint-order="stroke">${esc(v.name)}</text></g>`;
 }
 svg+='</g></svg>';$('#map').innerHTML=svg;
}

function modal(title,body,footer){stopAuto();$('#modal').innerHTML=`<div class="modalhead"><h2>${title}</h2><button class="ghost" data-action="close" aria-label="关闭弹窗">✕</button></div><div class="modalbody">${body}</div><div class="modalfoot">${footer||'<button data-action="close">关闭</button>'}</div>`;$('#modal').showModal();}
function close(){ $('#modal').close(); }
function eventDialog(){modal('注入业务事件',`<p class="sub">事件将改变实际业务状态，需重新生成并确认方案。</p><label for="eventKind">事件类型</label><select id="eventKind"><option value="overflow">垃圾满溢 · 新增30分钟截止清运任务</option><option value="complaint">临时投诉 · 新增45分钟截止清运任务</option><option value="failure">车辆故障 · 释放该车未完成任务</option><option value="congestion">东片区拥堵 · 通行时间2.5倍</option><option value="recovery">车辆恢复 · 恢复可用状态</option><option value="road_closed">道路封闭 · 按权限绕行</option><option value="facility_closed">设施关闭 · 重新选择补给站</option><option value="weather">天气变更 · 校验作业规则</option></select><label for="eventVehicle">目标车辆（故障 / 恢复时使用）</label><select id="eventVehicle">${state.vehicles.map(v=>`<option value="${esc(v.id)}">${esc(v.name)} · ${kinds[v.kind]}${!v.enabled?' · 故障':''}</option>`).join('')}</select><label for="eventRoad">封闭有向道路（道路事件）</label><select id="eventRoad">${state.edges.map(e=>`<option value="${esc(JSON.stringify([e.a,e.b]))}">${esc(e.a)} → ${esc(e.b)}</option>`).join('')}</select><label for="eventFacility">目标设施（设施关闭事件）</label><select id="eventFacility">${state.facilities.map(f=>`<option value="${esc(f.id)}">${esc(f.name)}</option>`).join('')}</select><label for="eventWeather">天气编码（天气事件，研究示例3=洗扫禁作业）</label><input id="eventWeather" type="number" min="0" max="10" value="3"><p class="help">满溢和投诉在合成点位新增任务。故障中断按原型规则处理，实际救援与载荷转运需在企业试点时建模。</p>`,`<button data-action="close">取消</button><button class="primary" data-action="event-submit">确认注入</button>`);}
function taskDetail(id){const t=state.tasks.find(t=>t.id===id);if(!t)return;const a=assignments()[id];modal(esc(t.name),[['编号',t.id],['任务类别',taskKinds[t.kind]],['起点 → 终点',`${t.start} → ${t.end}`],['最早开始 / 截止完成',`${clock(t.earliest)} / ${clock(t.deadline)}`],['服务时长',`${t.service} 分钟`],['载荷增量 / 耗水量',`${t.demand} t / ${t.water} m³`],['执行车辆',t.completed_by||(a?.vehicle?(state.draft?'候选 ':'')+a.vehicle:'未分配')],['车辆锁定',t.locked_to||'无'],['指定作业弧',(t.service_path||[t.start]).join(' → ')],['允许反向作业',t.reversible?'是':'否'],['资质要求',(t.skills||[]).join('、')||'未配置'],['风险截止',state.forecast?.tasks[t.id]?clock(state.forecast.tasks[t.id].deadline):'未生成'],['状态',{pending:'待执行',running:'执行中',done:'已完成'}[t.status]]].map(([k,v])=>`<div class="pair"><span>${k}</span><b>${esc(v)}</b></div>`).join(''));}
function manualDialog(id){const t=state.tasks.find(t=>t.id===id);modal('人工改派 · '+esc(id),`<p class="sub">为「${esc(t.name)}」选择兼容车辆，算法检查可行性后生成候选方案。</p><label for="manualVehicle">目标车辆</label><select id="manualVehicle">${state.vehicles.filter(v=>v.enabled&&v.kind===t.kind).map(v=>`<option value="${esc(v.id)}">${esc(v.name)} · 容量 ${v.capacity} t</option>`).join('')}</select><p class="help">执行中动作和冻结窗口内已承诺任务不可普通改派。确认候选后，任务会锁定到目标车辆。</p>`,`<button data-action="close">取消</button><button class="primary" data-action="manual-submit" data-task="${esc(id)}">检查并生成候选</button>`);}
async function download(path,name){try{const r=await fetch(path);if(!r.ok)throw new Error('导出失败');const blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){toast(e.message,true);}}
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-action],[data-nav]');if(!b)return;
 if(b.dataset.nav){page=b.dataset.nav;render();return;}
 const action=b.dataset.action;if(busy&&action!=='close')return;
 if(['plan','accept','reject','benchmark'].includes(action)){stopAuto();await act(action);return;}
 if(action==='close'){close();return;}
 if(action==='event-dialog'){eventDialog();return;}
 if(action==='event-submit'){const road=JSON.parse($('#eventRoad').value);const body={kind:$('#eventKind').value,vehicle:$('#eventVehicle').value,a:road[0],b:road[1],facility:$('#eventFacility').value,value:Number($('#eventWeather').value)};close();await act('event',body);return;}
 if(action==='advance'){await act('advance',{minutes:10});return;}
 if(action==='auto'){if(auto)stopAuto();else auto=setInterval(()=>{if(!busy)act('advance',{minutes:2});},1800);render();return;}
 if(action==='export'){download('/api/export',`环卫智枢-快照-r${state.revision}.json`);return;}
 if(action==='template'){download('/api/template','环卫智枢-场景模板.json');return;}
 if(action==='task-detail'){taskDetail(b.dataset.task);return;}
 if(action==='candidate-tasks'){filter='candidate';search='';page='tasks';render();return;}
 if(action==='select-vehicle'){if($('#modal').open)close();selected=b.dataset.vehicle;page='dashboard';render();return;}
 if(action==='lock'){await act('lock',{task:b.dataset.task});return;}
 if(action==='manual-dialog'){manualDialog(b.dataset.task);return;}
 if(action==='manual-submit'){const body={task:b.dataset.task,vehicle:$('#manualVehicle').value};close();page='dashboard';await act('manual',body);return;}
 if(action==='changes'){const p=state.draft||state.plan;if(state.draft){const view=buildPlanPreview(state);modal('候选方案全部改动',`<p class="help">比较当前剩余计划，包含新分配、车辆改派、顺序、时间、路线和补给变化。</p><div class="plan-modal-changes">${previewChanges(view)}</div>`);}else modal('已确认方案车辆改派记录',`<p class="help">此处为本方案确认前记录的跨车辆改派。</p><div class="detail-list">${(p.changes||[]).map(c=>`<div>${esc(c.task)}：${esc(c.from)} → ${esc(c.to)}</div>`).join('')||'<p>该方案未记录跨车辆改派。</p>'}</div>`);return;}
 if(action==='unassigned'){const p=state.draft||state.plan;modal('待人工处理任务',`<div class="detail-list">${p.unassigned.map(u=>`<div><b>${esc(u.id)}</b><br>${esc(u.reason)}</div>`).join('')||'<p>本次规划未发现无法分配的任务。</p>'}</div>`);return;}
 if(action.startsWith('zoom-')){zoom=action==='zoom-reset'?1:Math.min(2,Math.max(.8,zoom+(action==='zoom-in'?.2:-.2)));renderMap();return;}
 if(action==='reset-dialog'){modal('重置演示场景','将清空当前计划、执行进度和运行记录，恢复24辆车、120项任务的初始数据。建议先导出快照。','<button data-action="close">取消</button><button class="danger" data-action="reset-confirm">确认重置</button>');return;}
 if(action==='reset-confirm'){close();benchmark=null;await act('reset');return;}
 if(action==='import-dialog'){modal('导入场景','导入将开启新演示日，并替换当前数据和运行记录。请先导出快照。','<button data-action="close">取消</button><button class="primary" data-action="choose-file">选择 JSON 文件</button>');return;}
 if(action==='choose-file'){close();$('#fileInput').click();}
});
document.addEventListener('change',async e=>{
 if(e.target.id==='routeSelect'){selected=e.target.value;render();}
 if(e.target.id==='taskFilter'){filter=e.target.value;render();}
 if(e.target.id==='fileInput'){const f=e.target.files[0];if(!f)return;if(f.size>2_000_000){toast('文件需小于2MB',true);return;}try{const scenario=JSON.parse(await f.text());benchmark=null;await act('import',{scenario});}catch(err){toast('JSON 无法解析：'+err.message,true);}}
});
document.addEventListener('input',e=>{if(e.target.id==='search'){search=e.target.value;const list=filteredTasks();$('#task-results').innerHTML=taskTable(list);$('.count').textContent=`${list.length} 项任务`;}});
async function boot(){try{const response=await fetch('/api/state');if(!response.ok)throw new Error('服务未响应');state=await response.json();render();}catch(e){$('#app').innerHTML='<div class="errorbox">无法连接本地服务。请先运行启动脚本，再刷新页面。</div>';}}
boot();
