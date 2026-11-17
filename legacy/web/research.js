'use strict';
let historyPurpose='train';
function researchPage(){
 const cfg={freeze:10,horizon:120,budget:12,iterations:24,alpha:.9,theta_on:.65,theta_off:.35,cooldown:5,...state.settings};
 const report=state.prediction_report, fc=state.forecast, c=state.controller||{}, p=state.draft||state.plan;
 const fields=[['freeze','冻结长度 / 分钟',0,60,1],['horizon','滚动窗口 / 分钟',15,1440,1],['budget','搜索预算 / 秒',.5,60,.5],['iterations','ALNS迭代上限',0,500,1],['alpha','CVaR置信水平',.5,.99,.01],['theta_on','触发阈值',.1,1,.05],['theta_off','解除阈值',0,.9,.05],['cooldown','冷却时间 / 分钟',0,60,1]];
 return `<div class="compare-note">研究版 V0.2 · 全链路采用真实计算。模型来源：<b>${report?(report.source==='synthetic'?'合成训练数据':'用户导入历史数据'):'未训练（显式默认压力情景）'}</b>。现场验收、区间覆盖和重规划时延以实验结果为准。</div>
 <section class="workgrid"><div class="stack"><div class="card"><div class="cardhead"><h2>预测与校准</h2><span class="label">Quantile GBDT + CQR</span></div><div class="panelbody"><p>按时间顺序60%训练、20%校准、20%测试。四类目标：填充速率、通行系数、耗水系数、排队时长。分位数排序消除交叉，独立校准集扩展区间。</p><div class="actions"><button data-action="train-demo">训练合成示例</button><button data-action="history-upload">导入历史数据训练</button><button data-action="forecast">更新风险预测</button><button data-action="history-template">历史数据模板</button><button data-action="calibration-upload">导入观测滑动校准</button></div><input type="file" id="historyInput" accept=".json" hidden>
 ${report?`<p class="help">数据量 ${report.split.train} / ${report.split.calibration} / ${report.split.test}；目标覆盖率 ${(1-report.alpha)*100}%。覆盖保证依赖交换性，时间漂移下需实测。</p><table><thead><tr><th>目标</th><th>测试覆盖率</th><th>平均区间宽度</th></tr></thead><tbody>${Object.entries(report.metrics).map(([k,m])=>`<tr><td>${esc(k)}</td><td>${(m.coverage*100).toFixed(1)}%</td><td>${m.width.toFixed(4)}</td></tr>`).join('')}</tbody></table>`:'<p class="notice">尚无训练结果；不会把固定规则包装成预测模型。</p>'}
 ${report?.online_calibration?`<p class="notice">最近滑动校准 ${report.online_calibration.samples} 条；上表仍为原始独立测试结果，未用校准内拟合冒充新测试覆盖。</p>`:''}${fc?`<p>最近预测：${clock(fc.at)}。${Object.keys(fc.tasks).length}项待办生成区间；仅有箱体容量的任务才推导溢满截止期。</p><div class="tablewrap"><table><thead><tr><th>任务</th><th>填充速率区间</th><th>风险截止</th></tr></thead><tbody>${Object.entries(fc.tasks).slice(0,8).map(([id,x])=>`<tr><td>${esc(id)}</td><td>${x.fill_rate[0].toFixed(4)} — ${x.fill_rate[2].toFixed(4)}</td><td>${clock(x.deadline)}${x.capacity?'':'（规则）'}</td></tr>`).join('')}</tbody></table></div>`:''}</div></div>
 <div class="card"><div class="cardhead"><h2>搜索与安全验收</h2><span class="label">H-ALNS / CP-SAT</span></div><div class="panelbody"><div class="actions"><button data-action="solve-halns">H-ALNS求解</button><button data-action="solve-game">局部安全博弈</button><button data-action="control">分级恢复评估</button><button data-action="reference">小实例精确参照</button></div>${p?.version===2?`<p><b>安全盾：${p.shield?.passed?'通过':'拒绝'}</b> · 冻结 ${p.frozen.length} 项 · 窗口外 ${p.deferred.length} 项</p><p>三级目标 F1 / F2 / F3：<b>${p.objective.map(v=>v.toFixed(2)).join(' / ')}</b></p><p class="help">F1：强制漏收惩罚与期望加权迟到；F2：情景CVaR；F3：成本、能源代理与路线扰动。不同单位不可直接加总。</p><details><summary>查看算子权重、精确修复状态与迭代轨迹</summary><pre class="research-json">${esc(JSON.stringify({solver:p.solver,trace:p.trace,risk:p.risk,shield:p.shield},null,2))}</pre></details>`:'<p class="empty">尚无研究版计划，点击H-ALNS求解。</p>'}</div></div></div>
 <div class="stack"><div class="card"><div class="cardhead"><h2>弹性控制器</h2><span class="label orange">${esc(c.level||'L0')}</span></div><div class="panelbody"><p>综合风险：<b>${c.risk??'—'}</b></p><p>${esc(c.reason||'等待事件或状态更新')}</p><p class="help">L0保持 · L1绕行 · L2局部交换 · L3滚动重排 · L4人工/外援。自动控制只生成候选，仍需调度员确认。</p><label><input id="autoControl" type="checkbox" ${cfg.auto_control?'checked':''}> 随事件/时间推进自动评估</label>${fields.map(([k,label,min,max,step])=>`<label for="cfg-${k}">${label}</label><input id="cfg-${k}" type="number" min="${min}" max="${max}" step="${step}" value="${cfg[k]}">`).join('')}<button class="primary" data-action="save-settings">保存算法参数</button></div></div><div class="card"><div class="cardhead"><h2>精确参照模型</h2></div><div class="panelbody"><p class="help">固定6任务/3车辆小实例，静态整数时间、每车每设施最多2访次；不改变当前计划。</p>${state.reference_report?`<pre class="research-json">${esc(JSON.stringify(state.reference_report,null,2))}</pre>`:'<p>点击小实例精确参照，查看求解状态与上下界。</p>'}</div></div><div class="card"><div class="cardhead"><h2>人工与外援处置</h2></div><div class="panelbody"><label for="handoverKind">处置类型</label><select id="handoverKind"><option value="external">申请外援</option><option value="defer">延期处置</option><option value="support">跨区支援</option></select><label for="handoverNote">依据与安排</label><textarea id="handoverNote" placeholder="记录原因、责任人及后续安排"></textarea><button data-action="handover">登记处置</button><p class="help">登记只记录人工决定，不会伪造任务完成或外援车辆到场。</p></div></div></div></section>`;
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-action]');if(!b||busy)return;const a=b.dataset.action;
 if(a==='train-demo'){await act('train');return;}
 if(a==='forecast'||a==='control'){await act(a);return;}
 if(a==='reference'){await act('reference');return;}
 if(a==='history-template'){await download('/api/history-template','历史训练数据模板.json');return;}
 if(a==='history-upload'||a==='calibration-upload'){historyPurpose=a==='calibration-upload'?'recalibrate':'train';$('#historyInput').click();return;}
 if(a==='solve-halns'||a==='solve-game'){await act('plan',{strategy:a==='solve-game'?'game':'halns'});return;}
 if(a==='save-settings'){
  const keys=['freeze','horizon','budget','iterations','alpha','theta_on','theta_off','cooldown'];
  const data=Object.fromEntries(keys.map(k=>[k,Number($('#cfg-'+k).value)]));data.auto_control=$('#autoControl').checked;await act('settings',data);return;
 }
 if(a==='handover'){await act('handover',{decision:$('#handoverKind').value,note:$('#handoverNote').value});return;}
 if(a==='research-demo-dialog'){modal('载入研究场景','将重置为含驾驶员资质、双向作业弧、泊位、能源与箱体容量的合成示例。请先导出当前快照。','<button data-action="close">取消</button><button data-action="research-demo-confirm">确认载入</button>');return;}
 if(a==='research-demo-confirm'){close();benchmark=null;await act('research_demo');}
});
document.addEventListener('change',async e=>{
 if(e.target.id!=='historyInput')return;const file=e.target.files[0];if(!file)return;
 if(file.size>2_000_000){toast('历史文件需小于2MB',true);return;}
 try{const data=JSON.parse(await file.text());await act(historyPurpose,{rows:data.rows||data});}catch(error){toast(error.message,true);}
});
