"""Validate published Solomon routes independently of our optimization results."""
import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.public_benchmark import read_instance,verify
DATA=ROOT/'data/public-benchmarks'
refs=json.loads((DATA/'solomon-bks.json').read_text())['values'];checks=[]
for path in sorted((DATA/'bks-solutions').glob('*.txt')):
    p=read_instance(next((DATA/'solomon').rglob(path.name)))
    text=path.read_text(encoding='latin1')
    routes=[list(map(int,m.split())) for m in re.findall(r'^Route\s+\d+\s*:\s*([^\r\n]+)',text,re.M|re.I)]
    # Recompute distances directly from the full-precision matrix; use check's
    # cost result to compare with the publisher's two-decimal number separately.
    cost=sum(sum(p['dist'][a][b] for a,b in zip([0]+r,r+[0])) for r in routes)
    s={'routes':routes,'objective':(0,len(routes),cost),'unassigned':[]};c=verify(p,s)
    ref=refs[path.stem];c.update(instance=path.stem,reference=ref,rounded_distance_matches=abs(cost-ref['distance'])<=.00501,
                               fleet_matches=len(routes)==ref['vehicles'])
    checks.append(c)
result={'expected':56,'downloaded':len(checks),'checks':checks,
        'all_passed':len(checks)==56 and all(c['feasible'] and c['rounded_distance_matches'] and c['fleet_matches'] for c in checks)}
(DATA/'reference-verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'downloaded':len(checks),'all_passed':result['all_passed'],'failed':[c['instance'] for c in checks if not(c['feasible'] and c['rounded_distance_matches'] and c['fleet_matches'])]}))
