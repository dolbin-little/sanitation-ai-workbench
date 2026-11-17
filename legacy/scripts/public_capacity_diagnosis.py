"""Post-hoc CARP failure diagnosis. CP-SAT checks packing, not optimal routing.
Does not overwrite or retroactively improve the original comparison matrix.
"""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.public_benchmark import read_instance,NativeEvaluator,verify
from ortools.sat.python import cp_model
DATA=ROOT/'data/public-benchmarks';manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))['instances']
results=[]
for entry in manifest:
    if entry['kind']!='carp':continue
    file=DATA/'results/native-v1'/f"{entry['family']}--{entry['name']}.json"
    if not file.exists():continue
    rows=[r for r in json.loads(file.read_text()) if r['method']=='adaptive_alns']
    if all(r['check']['feasible'] for r in rows):continue
    p=read_instance(ROOT/entry['path']);n=p['n'];k=p['vehicles'];model=cp_model.CpModel()
    x=[[model.NewBoolVar(f'x{i}_{v}') for v in range(k)] for i in range(n)]
    for row in x:model.AddExactlyOne(row)
    loads=[]
    for v in range(k):
        load=sum(int(p['jobs'][i+1]['demand'])*x[i][v] for i in range(n))
        model.Add(load<=int(p['capacity']));loads.append(load)
    for a,b in zip(loads,loads[1:]):model.Add(a>=b)
    # All bins are interchangeable: place the largest item in the first bin.
    # Do not force this symmetry with load ordering: largest item need not be
    # in the maximally loaded bin, so only the load ordering above is imposed.
    solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=30.;solver.parameters.num_search_workers=1
    solver.parameters.random_seed=0;start=time.perf_counter();status=solver.Solve(model)
    row={'family':entry['family'],'instance':entry['name'],'status':solver.StatusName(status),
         'seconds':time.perf_counter()-start,'capacity_slack':k*p['capacity']-sum(j['demand'] for j in p['jobs'][1:]),
         'method':'post-hoc exact capacity feasibility only; no distance minimization','original_feasible_runs':sum(r['check']['feasible'] for r in rows)}
    if status in (cp_model.FEASIBLE,cp_model.OPTIMAL):
        routes=[[i+1 for i in range(n) if solver.Value(x[i][v])] for v in range(k)];routes=[r for r in routes if r]
        ev=NativeEvaluator(p);cost=sum(ev.route(tuple(r))[0] for r in routes)
        s={'routes':[list(ev.route(tuple(r))[1]) for r in routes],'objective':(0,cost),'unassigned':[]}
        row.update(solution=s,check=verify(p,s))
    results.append(row);print(entry['family'],entry['name'],row['status'],flush=True)
out=DATA/'results/capacity-diagnosis.json';out.write_text(json.dumps({'post_hoc':True,'cases':results},indent=2))
