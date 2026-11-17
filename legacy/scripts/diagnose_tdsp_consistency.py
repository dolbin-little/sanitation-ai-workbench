"""Reproducible consistency witness; does not alter source data or benchmark results."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.public_benchmark import arrival,raw_td_network,td_shortest,integrate_speed
from backend.public_td_compact import read_td
path=next((ROOT/'data/public-benchmarks/tdcarp').rglob('Type_H/C01.tdsp'))
p=read_td(path);adj,edges,factor=raw_td_network(path)
route=[1,2,34,33,35,37,46,45,44,43,39];departure=282.7490934003974
at=departure;published_at=departure;steps=[]
for u,v in zip(route,route[1:]):
    end=integrate_speed(edges[u,v],at)
    published_end=arrival(p['travel'][u,v],published_at)
    steps.append({'from':u,'to':v,'raw_depart':at,'raw_arrive':end,'composed_published_arrive':published_end})
    at=end;published_at=published_end
direct=arrival(p['travel'][route[0],route[-1]],departure)
shortest=td_shortest(adj,route[0],route[-1],departure)
assert abs(at-shortest)<1e-8
assert abs(at-published_at)<1e-5
assert direct-published_at>.2
report={'instance':'Type_H/C01','tdsp_sha256':p['sha256'],'departure':departure,'path':route,'steps':steps,
        'direct_published_arrival':direct,'raw_path_arrival':at,'composed_published_arrival':published_at,
        'raw_dijkstra_arrival':shortest,'difference':direct-at,
        'interpretation':'The supplied direct pair profile is later than a concrete path whose individual published pair profiles and raw speed integrals agree. Keep this as an input/preprocessing consistency issue; do not silently relax checker tolerance or claim all TDSP costs independently verified.'}
(ROOT/'data/public-benchmarks/tdsp-consistency-witness.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:report[k] for k in ('direct_published_arrival','raw_path_arrival','composed_published_arrival','difference')}))
