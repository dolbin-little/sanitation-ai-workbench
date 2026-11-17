"""Representative, paired CPU-budget sensitivity; deliberately separate from full suite."""
import concurrent.futures,hashlib,json,sys,time,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.public_benchmark_static_v1 import read_instance,solve,verify
DATA=ROOT/'data/public-benchmarks'
SELECTION={'Solomon':['c101','c201','r101','r201','rc101','rc201'],
           'gdb':['gdb1'],'bccm':['val1A'],'kshs':['kshs1'],'eglese':['egl-e1-A'],
           'TDCARP-Type_L':['C01'],'TDCARP-Type_M':['C01'],'TDCARP-Type_H':['C01']}

def worker(entry):
    p=read_instance(ROOT/entry['path']);rows=[]
    for seed in range(30):
        for budget in ((.5,10.) if seed%2==0 else (10.,.5)):
            s=solve(p,'adaptive_alns',seed,budget,200)
            rows.append({'family':entry['family'],'instance':entry['name'],'seed':seed,'budget_cpu':budget,
                         'solution':s,'check':verify(p,s)})
    return entry,rows

def main():
    out=DATA/'results/budget-sensitivity';out.mkdir(parents=True,exist_ok=True)
    entries=[e for e in json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))['instances'] if e['name'] in SELECTION[e['family']]]
    assert len(entries)==13
    protocol={'selection':SELECTION,'rationale':'first numbered instance in each Solomon class / CARP family / TD intensity, not chosen by favorable outcome',
              'seeds':30,'budgets_cpu_seconds':[.5,10.],'iterations':200,'method':'adaptive_alns',
              'code_sha256':hashlib.sha256((ROOT/'backend/public_benchmark_static_v1.py').read_bytes()).hexdigest(),
              'expected_new_runs':780,'main_budget_reference':'native-v1, 2 CPU seconds, same 200 iterations'}
    if (out/'protocol.json').exists():
        assert json.loads((out/'protocol.json').read_text())==protocol,'sensitivity protocol changed; use a new output directory'
    else:(out/'protocol.json').write_text(json.dumps(protocol,indent=2))
    todo=[e for e in entries if not (out/f"{e['family']}--{e['name']}.json").exists()]
    # Only small C01 TDSPs here. Four workers fit beside the main experiment.
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        for entry,rows in pool.map(worker,todo):
            (out/f"{entry['family']}--{entry['name']}.json").write_text(json.dumps(rows,separators=(',',':')))
            print(entry['family'],entry['name'],'finished',flush=True)
    results=[r for f in out.glob('*--*.json') for r in json.loads(f.read_text())]
    assert len(results)==780
    summary=[]
    for family,names in SELECTION.items():
        for name in names:
            for budget in (.5,10.):
                rows=[r for r in results if r['family']==family and r['instance']==name and r['budget_cpu']==budget]
                summary.append({'family':family,'instance':name,'budget_cpu':budget,'runs':len(rows),
                    'feasible':sum(r['check']['feasible'] for r in rows),'unassigned':sum(len(r['check']['unassigned']) for r in rows),
                    'mean_cpu':sum(r['solution']['cpu_seconds'] for r in rows)/len(rows),
                    'mean_iterations':sum(r['solution']['iterations'] for r in rows)/len(rows)})
    (out/'summary.json').write_text(json.dumps({'complete':True,'runs':len(results),'summary':summary},indent=2))

if __name__=='__main__':main()
