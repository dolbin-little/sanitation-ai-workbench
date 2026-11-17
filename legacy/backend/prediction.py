"""Quantile GBDT + split conformal calibration. JSON trees, no pickle uploads."""
import math
import random
from datetime import datetime

FEATURES = ['hour', 'weekday', 'weather', 'zone', 'base', 'kind']
TARGETS = ['fill_rate', 'travel_factor', 'water_factor', 'queue']


def synthetic_history(n=1000, seed=42):
    r = random.Random(seed)
    rows = []
    for i in range(n):
        x = [i % 24, (i//24) % 7, r.randrange(3), r.randrange(5), r.uniform(.3, 2.5), r.randrange(3)]
        peak = int(x[0] in (7, 8, 17, 18))
        rows.append(dict(at=i, x=x, y={
            'fill_rate': max(.0001, .003*x[4]+.001*x[3]+r.gauss(0,.001)),
            'travel_factor': max(.5, 1+.4*peak+.12*x[2]+r.gauss(0,.12)),
            'water_factor': max(.4, 1+.12*x[2]+.05*x[3]+r.gauss(0,.15)),
            'queue': max(0, 2+4*peak+x[3]+r.gauss(0,2))}))
    return rows


def vector(s, task=None):
    t = task or {}
    return [s['now']/60, s.get('weekday',0), s.get('weather',0), t.get('zone',0),
            t.get('demand',1), {'collection':0,'hook':1,'sweeper':2}.get(t.get('kind'),0)]


def predict_tree(tree, x):
    i = 0
    while tree['left'][i] != -1:
        i = tree['left'][i] if x[tree['feature'][i]] <= tree['threshold'][i] else tree['right'][i]
    return tree['value'][i]


def raw(model, x):
    return model['base'] + model['rate']*sum(predict_tree(t,x) for t in model['trees'])


def interval(bundle, target, x):
    m = bundle['models'][target]
    q = sorted(raw(a,x) for a in m['quantiles'])
    return [max(0,q[0]-m['gamma']), max(0,q[1]), max(0,q[2]+m['gamma'])]


def train(rows, source='imported', alpha=.1):
    from sklearn.ensemble import GradientBoostingRegressor
    if not isinstance(rows,list) or not 100 <= len(rows) <= 10000:
        raise ValueError('训练数据须有100—10000条，按时间划分训练/校准/测试集')
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('x'),list) or len(row['x'])!=6:
            raise ValueError('每行须含 at、六维 x、四目标 y')
        values = [row.get('at'),*row['x'],*(row.get('y',{}).get(k) for k in TARGETS)]
        if any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) for v in values):
            raise ValueError('训练数据必须为有限数值')
        if any(row['y'][k]<0 for k in TARGETS):
            raise ValueError('预测目标必须非负')
    rows = sorted(rows,key=lambda r:r['at'])
    a,b = int(len(rows)*.6),int(len(rows)*.8)
    if rows[a-1]['at'] >= rows[a]['at'] or rows[b-1]['at'] >= rows[b]['at']:
        raise ValueError('时间切分边界须严格分离，避免同一时刻泄漏')
    fit,cal,test=rows[:a],rows[a:b],rows[b:]
    bundle = dict(source=source, features=FEATURES, alpha=alpha, models={},
                  split={'train':a,'calibration':b-a,'test':len(test)},trained_at=datetime.now().isoformat())
    bundle['time_ranges']={'train_end':fit[-1]['at'],'calibration_end':cal[-1]['at'],'test_end':test[-1]['at']}
    for target in TARGETS:
        models=[]
        for q in (alpha/2,.5,1-alpha/2):
            reg=GradientBoostingRegressor(loss='quantile',alpha=q,n_estimators=35,max_depth=2,random_state=42)
            reg.fit([r['x'] for r in fit],[r['y'][target] for r in fit])
            trees=[]
            for estimator in reg.estimators_[:,0]:
                t=estimator.tree_
                trees.append(dict(left=t.children_left.tolist(),right=t.children_right.tolist(),
                    feature=t.feature.tolist(),threshold=t.threshold.tolist(),value=t.value[:,0,0].tolist()))
            models.append(dict(base=float(reg.init_.constant_[0,0]),rate=reg.learning_rate,trees=trees))
        scores=[]
        for r in cal:
            qs=sorted(raw(m,r['x']) for m in models)
            scores.append(max(qs[0]-r['y'][target],r['y'][target]-qs[2],0))
        rank=math.ceil((len(scores)+1)*(1-alpha))
        gamma=sorted(scores)[min(rank,len(scores))-1]
        bundle['models'][target]=dict(quantiles=models,gamma=gamma)
        covered=[]; widths=[]; groups={}
        for r in test:
            lo,mid,hi=interval(bundle,target,r['x']); ok=lo<=r['y'][target]<=hi
            covered.append(ok); widths.append(hi-lo)
            key=f"weather={r['x'][2]};zone={r['x'][3]}"
            groups.setdefault(key,[]).append(ok)
        bundle['models'][target]['metrics']=dict(coverage=sum(covered)/len(covered),width=sum(widths)/len(widths),
            groups={k:dict(n=len(v),coverage=sum(v)/len(v)) for k,v in groups.items()})
    return bundle


def forecast(s, bundle):
    result={'source':bundle['source'],'at':s['now'],'tasks':{},'global':{},'alpha':bundle['alpha']}
    for name in ('travel_factor','water_factor','queue'):
        result['global'][name]=interval(bundle,name,vector(s))
    for t in s['tasks']:
        if t['status']!='pending': continue
        rate=interval(bundle,'fill_rate',vector(s,t))
        deadline=t.get('rule_deadline',t['deadline'])
        cap=t.get('bin_capacity')
        if cap and rate[2]>0:
            remaining=max(0,cap*(1-t.get('safety_margin',.1))-t.get('fill',t['demand']))
            deadline=min(deadline,s['now']+remaining/rate[2])
        result['tasks'][t['id']]={'fill_rate':rate,'deadline':deadline,
            'water':interval(bundle,'water_factor',vector(s,t)),'capacity':cap}
    return result


def recalibrate(bundle, rows, window=200):
    """Sliding labeled calibration window; never labels its in-window fit as test coverage."""
    if not isinstance(rows,list) or not 20<=len(rows)<=10000:raise ValueError('滑动校准需要20—10000条已观测样本')
    rows=sorted(rows,key=lambda r:r['at'])[-window:]
    if bundle.get('time_ranges') and rows[0]['at']<=bundle['time_ranges']['test_end']:
        raise ValueError('在线观测时间须晚于原独立测试集，不能复用测试样本调校')
    for row in rows:
        vals=[row.get('at'),*row.get('x',[]),*(row.get('y',{}).get(k) for k in TARGETS)]
        if len(row.get('x',[]))!=6 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in vals):raise ValueError('滑动校准样本字段无效')
        if any(row['y'][k]<0 for k in TARGETS):raise ValueError('校准目标必须非负')
    scores_by_target={}
    for target,model in bundle['models'].items():
        scores=[]
        for row in rows:
            q=sorted(raw(m,row['x']) for m in model['quantiles']);y=row['y'][target]
            scores.append(max(q[0]-y,y-q[2],0))
        rank=math.ceil((len(scores)+1)*(1-bundle['alpha']))
        model['gamma']=sorted(scores)[min(rank,len(scores))-1];scores_by_target[target]=model['gamma']
    report={'samples':len(rows),'start':rows[0]['at'],'end':rows[-1]['at'],'gamma':scores_by_target,
            'note':'滑动窗口重校准；不是独立测试覆盖率，时间漂移下无无条件覆盖保证'}
    bundle['online_calibration']=report
    return report
