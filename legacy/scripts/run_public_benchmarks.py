"""Resumable native 203-instance paired-seed experiment. Every failure is retained."""
import argparse,concurrent.futures,datetime,hashlib,json,os,platform,sys,time,traceback,multiprocessing,gc
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.public_benchmark import read_instance,solve,verify
from backend.public_td_compact import read_td
from backend.public_benchmark_static_v1 import solve as static_solve
METHODS=('nearest','insertion','static_alns','adaptive_alns')
TD_LOCK=None

def initialize(lock):
    global TD_LOCK
    TD_LOCK=lock


def worker(job):
    if job[0]['kind']=='tdcarp':
        with TD_LOCK:
            result=execute(job);gc.collect();return result
    result=execute(job);gc.collect();return result


def execute(job):
    entry,args=job;p=(read_td if entry['kind']=='tdcarp' else read_instance)(ROOT/entry['path']);rows=[]
    for seed in range(args['seeds']):
        # Rotate method execution order to mitigate systematic thermal/load effects.
        methods=METHODS[seed%4:]+METHODS[:seed%4]
        for method in methods:
            row={'instance':entry['name'],'family':entry['family'],'sha256':entry['sha256'],
                 'seed':seed,'method':method,'tasks':p['n']}
            try:
                solver=solve if entry['kind']=='tdcarp' else static_solve
                result=solver(p,method,seed,args['budget'],args['iterations']);check=verify(p,result)
                row.update(status='ok',solution=result,check=check)
            except Exception:
                row.update(status='error',error=traceback.format_exc())
            rows.append(row)
    return entry,rows


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--seeds',type=int,default=30)
    ap.add_argument('--budget',type=float,default=2.);ap.add_argument('--iterations',type=int,default=200)
    ap.add_argument('--workers',type=int,default=8);ap.add_argument('--output',default='native-v1')
    ap.add_argument('--limit',type=int,default=0);args=ap.parse_args();out=ROOT/'data/public-benchmarks/results'/args.output;out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((ROOT/'data/public-benchmarks/manifest.json').read_text(encoding='utf-8'))
    entries=manifest['instances'][:args.limit or None]
    protocol={'args':vars(args),'methods':METHODS,'instance_count':len(entries),'expected_runs':len(entries)*args.seeds*4,
              'cpu_budget_includes_construction':True,'construction_may_overrun':True,'iteration_limit':args.iterations,
              'python':sys.version,'platform':platform.platform(),'cpu_count':os.cpu_count(),
              'code_sha256':hashlib.sha256((ROOT/'backend/public_benchmark.py').read_bytes()).hexdigest(),
              'solver_versions':{
                  'static_families':{'file':'backend/public_benchmark_static_v1.py','sha256':hashlib.sha256((ROOT/'backend/public_benchmark_static_v1.py').read_bytes()).hexdigest()},
                  'TDCARP':{'file':'backend/public_benchmark.py','sha256':hashlib.sha256((ROOT/'backend/public_benchmark.py').read_bytes()).hexdigest(),'change':'reject destroy moves yielding infeasible partial routes under non-triangle published TDSP profiles'}},
              'td_reader':{'file':'backend/public_td_compact.py','sha256':hashlib.sha256((ROOT/'backend/public_td_compact.py').read_bytes()).hexdigest(),'concurrency':4},
              'manifest_sha256':hashlib.sha256((ROOT/'data/public-benchmarks/manifest.json').read_bytes()).hexdigest(),
              'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'track':'native subproblem ALNS port; not full municipal forecasting/control algorithm',
              'reference_objectives':{'Solomon':'min vehicles, then double-precision Euclidean distance; hard service-start windows',
                  'CARP':'fixed maximum fleet, total service+deadhead cost','TDCARP':'fixed maximum fleet, total route duration at departure 0; hard end horizon'},
              'tuning':'fixed preset parameters; no BKS routes or objective values supplied to solver'}
    pp=out/'protocol.json'
    if pp.exists():
        old=json.loads(pp.read_text())
        for key in ('args','code_sha256','manifest_sha256'):assert old[key]==protocol[key],f'resume mismatch: {key}'
        for family,version in old.get('solver_versions',{}).items():
            assert version['sha256']==protocol['solver_versions'][family]['sha256'],f'resume solver mismatch: {family}'
        if old.get('td_reader'):
            assert old['td_reader']['sha256']==protocol['td_reader']['sha256'],'resume TD reader mismatch'
    else:pp.write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    todo=[];done=0
    for entry in entries:
        name=f"{entry['family']}--{entry['name']}.json"
        if (out/name).exists():
            existing=json.loads((out/name).read_text());assert len(existing)==args.seeds*4;done+=1
        else:todo.append((entry,vars(args)))
    print(f'resume {done}/{len(entries)}',flush=True)
    # Limit compact TDSP readers to four simultaneous instances to avoid paging;
    # per-solver budgets use process CPU time, not wall time.
    lock=multiprocessing.Semaphore(4)
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers,initializer=initialize,initargs=(lock,)) as pool:
        futures=[pool.submit(worker,job) for job in todo]
        for fut in concurrent.futures.as_completed(futures):
            entry,rows=fut.result();name=f"{entry['family']}--{entry['name']}.json";path=out/name
            tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(rows,separators=(',',':')),encoding='utf-8');tmp.replace(path)
            done+=1;print(f"{done}/{len(entries)} {entry['family']} {entry['name']} feasible={sum(r.get('check',{}).get('feasible',False) for r in rows)}/{len(rows)}",flush=True)
    (out/'COMPLETE.json').write_text(json.dumps({'completed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'instances':done,'runs':done*args.seeds*4}),encoding='utf-8')

if __name__=='__main__':main()
