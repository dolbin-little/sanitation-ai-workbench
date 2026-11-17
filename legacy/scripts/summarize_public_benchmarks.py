"""Failure-aware summaries; inference is clustered by instance, not pseudo-replicated seeds."""
import argparse,csv,html,json,math,random,statistics,sys
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import backend
from scipy.stats import wilcoxon,friedmanchisquare,rankdata
METHODS=('nearest','insertion','static_alns','adaptive_alns')


def stats(x,bootstrap=True):
    if not x:return None
    rng=random.Random(42);boots=sorted(statistics.mean(rng.choices(x,k=len(x))) for _ in range(2000)) if bootstrap else None
    return {'n':len(x),'mean':statistics.mean(x),'median':statistics.median(x),'ci95':[boots[49],boots[1949]] if boots else None,
            'p95':sorted(x)[min(len(x)-1,math.ceil(.95*len(x))-1)]}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',default='native-v1');args=ap.parse_args()
    folder=ROOT/'data/public-benchmarks/results'/args.output
    protocol=json.loads((folder/'protocol.json').read_text());raw=[]
    for path in sorted(folder.glob('*--*.json')):raw.extend(json.loads(path.read_text()))
    bks=json.loads((ROOT/'data/public-benchmarks/solomon-bks.json').read_text())['values']
    records=[];groups=defaultdict(list);instances=defaultdict(list)
    for row in raw:
        s=row.get('solution',{});c=row.get('check',{});ok=c.get('feasible',False)
        rec={k:row[k] for k in ('family','instance','seed','method','tasks','status')}
        rec.update(feasible=ok,valid_partial=c.get('valid_partial',False),covered=c.get('covered',0),
                   unassigned=len(c.get('unassigned',list(range(row['tasks'])))),vehicles=c.get('vehicles'),cost=c.get('cost'),
                   cpu_seconds=s.get('cpu_seconds'),wall_seconds=s.get('runtime_seconds'),iterations=s.get('iterations'),
                   errors=';'.join(c.get('errors',[])) or row.get('error',''),vehicle_gap=None,distance_gap_percent=None)
        rec['physical_feasible']=(row['status']=='ok' and not c.get('unassigned') and all(e=='cost_mismatch' for e in c.get('errors',[])))
        if row['family']=='Solomon' and ok:
            ref=bks[row['instance']];rec['vehicle_gap']=c['vehicles']-ref['vehicles']
            if rec['vehicle_gap']==0:rec['distance_gap_percent']=100*(c['cost']/ref['distance']-1)
        records.append(rec);groups[row['family'],row['method']].append(rec)
        instances[row['family'],row['instance'],row['method']].append(rec)
    with (folder/'runs.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    summaries=[]
    for (family,method),rs in groups.items():
        summaries.append({'family':family,'method':method,'runs':len(rs),'feasible':sum(r['feasible'] for r in rs),
            'physical_feasible':sum(r['physical_feasible'] for r in rs),
            'hard_invalid':sum(not r['valid_partial'] for r in rs),'unassigned_total':sum(r['unassigned'] for r in rs),
            'cpu':stats([r['cpu_seconds'] for r in rs if r['cpu_seconds'] is not None],False),
            'vehicles_on_feasible':stats([r['vehicles'] for r in rs if r['feasible']],False),
            'vehicle_gap_on_feasible':stats([r['vehicle_gap'] for r in rs if r['vehicle_gap'] is not None],False),
            'distance_gap_at_BKS_fleet':stats([r['distance_gap_percent'] for r in rs if r['distance_gap_percent'] is not None],False)})
    per_instance=[]
    for (family,instance,method),rs in instances.items():
        per_instance.append({'family':family,'instance':instance,'method':method,'runs':len(rs),
            'feasible':sum(r['feasible'] for r in rs),'mean_unassigned':statistics.mean(r['unassigned'] for r in rs),
            'mean_cost_feasible':statistics.mean([r['cost'] for r in rs if r['feasible']]) if any(r['feasible'] for r in rs) else None,
            'mean_cpu':statistics.mean(r['cpu_seconds'] for r in rs if r['cpu_seconds'] is not None)})
    with (folder/'instances.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(per_instance[0]));w.writeheader();w.writerows(per_instance)
    pairs=[]
    for family in sorted({r['family'] for r in records}):
        names=sorted({r['instance'] for r in records if r['family']==family})
        for baseline in METHODS[:-1]:
            diffs=[];coverage=[];excluded=0
            for name in names:
                a=sorted(instances[family,name,'adaptive_alns'],key=lambda r:r['seed'])
                b=sorted(instances[family,name,baseline],key=lambda r:r['seed'])
                assert [r['seed'] for r in a]==[r['seed'] for r in b]
                coverage.append(statistics.mean(x['unassigned']-y['unassigned'] for x,y in zip(a,b)))
                # Strict complete-instance conditioning: all paired seeds feasible;
                # VRPTW also needs equal fleet size for every paired comparison.
                eligible=all(x['feasible'] and y['feasible'] and (family!='Solomon' or x['vehicles']==y['vehicles']) for x,y in zip(a,b))
                if eligible:diffs.append(statistics.mean(100*(x['cost']/y['cost']-1) for x,y in zip(a,b)))
                else:excluded+=1
            p=float(wilcoxon(diffs).pvalue) if diffs and any(diffs) else 1.
            pairs.append({'family':family,'baseline':baseline,'instance_clustered_percent_cost_delta':stats(diffs),
                          'excluded_instances_from_cost_comparison':excluded,'unassigned_delta_all_instances':stats(coverage),
                          'wilcoxon_p':p,'effect_dz':statistics.mean(diffs)/statistics.stdev(diffs) if len(diffs)>1 and statistics.stdev(diffs)>0 else None})
    running=0.
    for i,pair in enumerate(sorted(pairs,key=lambda p:p['wilcoxon_p'])):
        running=max(running,min(1.,pair['wilcoxon_p']*(len(pairs)-i)));pair['holm_p']=running
    rank_rows=[]
    for family,name in sorted({(r['family'],r['instance']) for r in records}):
        seedranks=[]
        for seed in range(protocol['args']['seeds']):
            rs=[next(r for r in instances[family,name,m] if r['seed']==seed) for m in METHODS]
            keys=[(not r['valid_partial'],r['unassigned'],r['vehicles'] if family=='Solomon' else 0,r['cost'] if r['cost'] is not None else math.inf) for r in rs]
            levels=sorted(set(keys));seedranks.append(list(rankdata([levels.index(k) for k in keys])))
        rank_rows.append([statistics.mean(row[i] for row in seedranks) for i in range(4)])
    friedman=None
    if len(rank_rows)>2 and any(len(set(r))>1 for r in rank_rows):
        t=friedmanchisquare(*zip(*rank_rows));friedman={'statistic':float(t.statistic),'p':float(t.pvalue),'blocks':'instances; seed-averaged lexicographic ranks','n':len(rank_rows)}
    result={'complete':len(raw)==protocol['expected_runs'] and (folder/'COMPLETE.json').exists(),
            'expected_runs':protocol['expected_runs'],'actual_runs':len(raw),'summary':summaries,'paired':pairs,'friedman':friedman,
            'limits':['Native benchmark ALNS port is not backend.optimizer.solve_v2.',
                      'No prediction calibration, game, CP-SAT repair, municipal rolling recovery, or field adoption claim is supported by this track.',
                      'Short CPU budgets are not comparable to published solvers with longer budgets.',
                      'Distance gaps are reported only at the same Solomon BKS fleet size; cost tests exclude entire instances with infeasible or unequal-fleet pairs.',
                      'CARP and TDCARP have no verified BKS table imported; no optimality gap is invented.',
                      'Some supplied TDCARP pair profiles disagree with a concrete raw-network path; cost_mismatch runs remain failed checks, not silently accepted. See tdsp-consistency-witness.json.']}
    budget_path=ROOT/'data/public-benchmarks/results/budget-sensitivity/summary.json'
    result['budget_sensitivity']=json.loads(budget_path.read_text()) if budget_path.exists() else None
    result['reference_verification']=json.loads((ROOT/'data/public-benchmarks/reference-verification.json').read_text()) if (ROOT/'data/public-benchmarks/reference-verification.json').exists() else None
    diagnosis_path=ROOT/'data/public-benchmarks/results/capacity-diagnosis.json'
    result['post_hoc_capacity_diagnosis']=json.loads(diagnosis_path.read_text()) if diagnosis_path.exists() else None
    (folder/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=''.join('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in (s['family'],s['method'],s['runs'],f"{s['physical_feasible']}/{s['runs']}",f"{s['feasible']}/{s['runs']}",s['hard_invalid'],s['unassigned_total'],round(s['cpu']['mean'],3)))+'</tr>' for s in summaries)
    compare=''.join('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in (p['family'],p['baseline'],p['instance_clustered_percent_cost_delta']['n'] if p['instance_clustered_percent_cost_delta'] else 0,
        round(p['instance_clustered_percent_cost_delta']['mean'],2) if p['instance_clustered_percent_cost_delta'] else '不可比',p['excluded_instances_from_cost_comparison'],round(p['holm_p'],5)))+'</tr>' for p in pairs)
    solomon_rows=''
    for s in summaries:
        if s['family']!='Solomon':continue
        fleet=s['vehicle_gap_on_feasible'];distance=s['distance_gap_at_BKS_fleet']
        solomon_rows+='<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in (s['method'],s['feasible'],
            round(fleet['mean'],3) if fleet else '—',distance['n'] if distance else 0,round(distance['mean'],2) if distance else '不可比'))+'</tr>'
    budget_note=''
    if result['budget_sensitivity']:
        budget_note=f'<div class="card"><h2>额外计算预算实验</h2><p>13 个代表实例 × 30 种子 × 0.5 / 10 秒，共 {result["budget_sensitivity"]["runs"]} 次已完成。与主实验分开归档，仍保留 200 次迭代上限。原始文件在 results/budget-sensitivity，具体数字也收录在本报告的 summary.json。</p></div>'
    if result['post_hoc_capacity_diagnosis']:
        cases=result['post_hoc_capacity_diagnosis']['cases'];solved=sum(c.get('check',{}).get('feasible',False) for c in cases)
        budget_note+=f'<div class="card"><h2>失败原因诊断</h2><p>对自适应 ALNS 出现漏服务的 {len(cases)} 个静态 CARP 实例，额外用 CP-SAT 检查容量分组；{solved} 个找到完整可行路线。说明这些失败至少可归因于当前搜索的装载构造/修复不足，不能解释成原始数据无解。这是事后诊断，不回填主实验，不证明路线成本最优。</p></div>'
    doc=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>环卫智枢 · 公开基准实验</title>
<style>body{{font:16px system-ui;margin:36px auto;max-width:1150px;color:#19323a;background:#f5f8f8}}h1{{font-size:30px}}.card{{background:white;padding:24px;margin:20px 0;border-radius:12px}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:9px;text-align:left;border-bottom:1px solid #dce7e6}}th{{background:#e6f3ef}}.flag{{color:#926000}}a{{color:#06756a}}</style>
<h1>公开基准实验 · 原生约束轨道</h1><p>已完成 {len(raw):,} / {protocol['expected_runs']:,} 次；状态：{'完成' if result['complete'] else '运行中'}。</p>
<div class="card"><b>范围</b><p>Solomon 56、CARP 87、TDCARP 60 个实例，每例 30 个配对种子。约束、单位和目标遵循原数据，不按环卫平台规则缩放。每次保留实际路线和独立检查结果。</p>
<p class="flag">这里验证的是原生子问题 ALNS 实现。不能据此声称平台的预测、博弈、精确修复、滚动恢复已通过公开基准验证，也不能将短预算成绩称为达到文献最优。</p></div>
<div class="card"><h2>全量结果</h2><p>不丢弃失败或漏服务。“原始约束满足”要求全部任务完成、原始路网重放的硬约束通过；“成本也一致”还要求成本数值一致。TDCARP 部分作者预计算到达函数与原始速度路径重算值不同，cost_mismatch 保留为验算失败；不能把这类数据一致性问题一概解释成路线超载或超时。配对检验仍采用预定的严格通过口径，没有事后放宽。</p><img src="feasibility.png" alt="按数据集和方法分类的完整性与验算结果" style="width:100%;height:auto"><p><a href="feasibility.pdf">导出 PDF 图</a> · <a href="feasibility.svg">导出 SVG 图</a></p><table><tr><th>数据集</th><th>方法</th><th>次数</th><th>原始约束满足</th><th>成本也一致</th><th>验算不一致/异常</th><th>未服务累计</th><th>平均 CPU 秒</th></tr>{rows}</table></div>
<div class="card"><h2>与 Solomon 官方参考的差距</h2><p>先比较车辆数。只有车辆数与参考相同的运行才计算距离差距；各方法的条件子集不同，不能直接把这一列当作方法间胜率。这里给描述性均值，配对推断见下一表。</p><table><tr><th>方法</th><th>完整可行次数</th><th>平均多用车辆</th><th>等参考车数的次数</th><th>该子集距离差距 %</th></tr>{solomon_rows}</table></div>
<div class="card"><h2>配对质量比较</h2><p>自适应 ALNS 相对基线的成本变化，负值更好。统计单位为实例，30 次种子先在实例内平均；只比较全部配对可行的实例，Solomon 还要求每对车辆数相同。多重检验采用 Holm 校正。</p><table><tr><th>数据集</th><th>基线</th><th>可比实例</th><th>成本变化 %</th><th>排除实例</th><th>Holm p</th></tr>{compare}</table></div>
{budget_note}<div class="card"><h2>数据来源与复核文件</h2><p><a href="https://www.sintef.no/projectweb/top/vrptw/100-customers/">SINTEF · Solomon</a> · <a href="https://www.uv.es/belengue/carp.html">Valencia · CARP</a> · <a href="https://github.com/vidalt/HGS-TDCARP">论文作者 · TDCARP</a></p><p><a href="runs.csv">逐次结果 CSV</a> · <a href="instances.csv">逐实例 CSV</a> · <a href="summary.json">统计及置信区间</a> · <a href="protocol.json">运行协议</a> · <a href="hardware.json">机器与依赖</a> · <a href="integrity-audit.json">完成后完整性核对</a> · <a href="tdsp-consistency-witness.json">TDCARP 一致性证据</a></p><p>同目录的“数据集--实例.json”含完整路线、随机种子、求解轨迹与验算结果。56 份 Solomon 官方参考路线已全部独立复核，重算值与官方表一致。</p></div></html>'''
    (folder/'report.html').write_text(doc,encoding='utf-8');print(json.dumps({'runs':len(raw),'complete':result['complete'],'report':str(folder/'report.html')},ensure_ascii=True))

if __name__=='__main__':main()
