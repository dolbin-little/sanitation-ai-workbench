"""Check exact planned matrix, unique keys, source/code hashes, retained failures."""
import hashlib,json,sys
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data/public-benchmarks';OUT=DATA/'results/native-v1'
manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'));protocol=json.loads((OUT/'protocol.json').read_text())
assert hashlib.sha256((DATA/'manifest.json').read_bytes()).hexdigest()==protocol['manifest_sha256']
for v in protocol['solver_versions'].values():
    assert hashlib.sha256((ROOT/v['file']).read_bytes()).hexdigest()==v['sha256']
expected={(e['family'],e['name'],seed,method) for e in manifest['instances']
          for seed in range(30) for method in protocol['methods']}
seen=set();errors=Counter();counts=Counter();violations=Counter()
for e in manifest['instances']:
    assert hashlib.sha256((ROOT/e['path']).read_bytes()).hexdigest()==e['sha256']
    file=OUT/f"{e['family']}--{e['name']}.json";rows=json.loads(file.read_text())
    assert len(rows)==120
    for r in rows:
        key=(r['family'],r['instance'],r['seed'],r['method']);assert key not in seen;seen.add(key)
        assert r['sha256']==e['sha256'] and r['tasks']==e['n']
        counts['runs']+=1
        if r['status']=='error':errors[r['error'].splitlines()[-1]]+=1;continue
        c=r['check'];s=r['solution'];assigned=[abs(i) for route in s['routes'] for i in route]
        assert set(assigned)|set(s['unassigned'])==set(range(1,e['n']+1))
        assert set(assigned).isdisjoint(s['unassigned'])
        assert len(set(assigned))==len(assigned)
        assert c['unassigned']==s['unassigned']
        assert s['objective'][0]==len(s['unassigned'])
        assert c['covered']==len(assigned)
        assert c['feasible']==(not c['errors'] and not c['unassigned'])
        counts['verified_complete']+=c['feasible'];counts['with_unassigned']+=bool(c['unassigned'])
        counts['physical_feasible']+=not c['unassigned'] and all(e=='cost_mismatch' for e in c['errors'])
        violations.update(c['errors'])
assert seen==expected,(len(seen),len(expected))
assert len(seen)==24360 and (OUT/'COMPLETE.json').exists()
budget=DATA/'results/budget-sensitivity';brows=[r for f in budget.glob('*--*.json') for r in json.loads(f.read_text())]
bkeys={(r['family'],r['instance'],r['seed'],r['budget_cpu']) for r in brows}
assert len(brows)==len(bkeys)==780
bp=json.loads((budget/'protocol.json').read_text())
assert hashlib.sha256((ROOT/'backend/public_benchmark_static_v1.py').read_bytes()).hexdigest()==bp['code_sha256']
bexpected={(family,name,seed,b) for family,names in bp['selection'].items() for name in names for seed in range(bp['seeds']) for b in bp['budgets_cpu_seconds']}
assert bkeys==bexpected
result={'matrix_complete':True,'unique_main_runs':len(seen),'unique_budget_runs':len(bkeys),
        'source_hashes_verified':203,'solver_hashes_verified':True,'counts':dict(counts),
        'exceptions':dict(errors),'check_errors':dict(violations),
        'note':'Matrix completion does not mean every route is feasible or every cost passes verification.'}
(OUT/'integrity-audit.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
