import math
from .model import DEFAULTS


def validate_settings(data):
    if not isinstance(data,dict) or set(data)-set(DEFAULTS):raise ValueError('未知算法设置字段')
    rules={'freeze':(0,60),'horizon':(15,1440),'iterations':(0,500),'budget':(.5,60),'seed':(0,1000000),
           'alpha':(.5,.99),'theta_on':(.1,1),'theta_off':(0,.9),'cooldown':(0,60),'exact_every':(0,100),
           'drop_penalty':(1,1e7),'energy_weight':(0,100),'stability_weight':(0,100)}
    for k,v in data.items():
        if k in ('auto_control','forecast_enabled','risk_enabled'):
            if not isinstance(v,bool):raise ValueError(k+'必须为布尔值')
        elif isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not rules[k][0]<=v<=rules[k][1]:raise ValueError(k+'超出范围')
        elif k in ('freeze','horizon','iterations','seed','cooldown','exact_every') and int(v)!=v:raise ValueError(k+'必须为整数')
    cfg={**DEFAULTS,**data}
    if cfg['theta_off']>=cfg['theta_on']:raise ValueError('关闭阈值必须小于开启阈值')
    return cfg


def validate_extensions(d):
    def num(r,k,lo,hi):
        if k not in r:return
        v=r[k]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError(k+'字段范围不合法')
    def strings(r,k,allowed=None):
        if k not in r:return
        a=r[k]
        if not isinstance(a,list) or any(not isinstance(x,str) for x in a) or (allowed is not None and not set(a)<=set(allowed)):raise ValueError(k+'列表不合法')
    kinds=['collection','hook','sweeper'];pairs={(e['a'],e['b']) for e in d['edges']}
    if 'settings' in d:d['settings']=validate_settings(d['settings'])
    num(d,'weather',0,10)
    for e in d['edges']:
        strings(e,'allowed_kinds',kinds);num(e,'max_weight',0,1000)
        if 'traffic' in e:
            if not isinstance(e['traffic'],list) or len(e['traffic'])>24:raise ValueError('traffic最多24段')
            last=0
            for seg in sorted(e['traffic'],key=lambda x:x['start']):
                for k in ('start','end','factor'):
                    if k not in seg:raise ValueError('traffic字段缺失')
                num(seg,'start',0,1440);num(seg,'end',0,1440);num(seg,'factor',.1,10)
                if seg['start']<last or seg['end']<=seg['start']:raise ValueError('traffic区间重叠/倒置')
                last=seg['end']
    for t in d['tasks']:
        strings(t,'skills');num(t,'hard_end',0,1440);num(t,'energy',0,1000);num(t,'bin_capacity',.01,100)
        num(t,'fill',0,100);num(t,'safety_margin',0,.9);num(t,'benefit',0,100000)
        if 'service_path' in t:
            p=t['service_path']
            if not isinstance(p,list) or not p or p[0]!=t['start'] or p[-1]!=t['end'] or any((a,b) not in pairs for a,b in zip(p,p[1:])):raise ValueError('service_path须为连续的真实有向服务弧')
            if t.get('reversible') and any((b,a) not in pairs for a,b in zip(p,p[1:])):raise ValueError('双向服务缺少反向道路')
        for k in ('mandatory','reversible'):
            if k in t and not isinstance(t[k],bool):raise ValueError(k+'必须为布尔值')
        if 'forbidden_weather' in t and (not isinstance(t['forbidden_weather'],list) or any(not isinstance(x,int) for x in t['forbidden_weather'])):raise ValueError('天气规则须为整数列表')
    for v in d['vehicles']:
        for k,lo,hi in [('shift_start',0,1440),('max_overtime',0,120),('energy_capacity',.1,10000),('energy_per_km',0,100),('weight',0,1000)]:num(v,k,lo,hi)
        if v.get('shift_start',0)>=v['shift_end']:raise ValueError('车辆班次倒置')
        if 'energy_capacity' in v:v['energy']=v['energy_capacity']
    for f in d['facilities']:
        strings(f,'resets',['load','water','energy']);num(f,'bays',1,100)
        if 'bays' in f and int(f['bays'])!=f['bays']:raise ValueError('泊位数量须为整数')
    if 'personnel' in d:
        ps=d['personnel']
        if not isinstance(ps,list) or len(ps)>500:raise ValueError('人员数量超限')
        seen=set()
        for p in ps:
            if not isinstance(p,dict) or not isinstance(p.get('id'),str) or p['id'] in seen:raise ValueError('人员ID无效/重复')
            seen.add(p['id']);strings(p,'licenses',kinds);strings(p,'skills')
            for k in ('shift_start','shift_end'):
                if k not in p:raise ValueError('人员班次缺失')
                num(p,k,0,1440)
            if p['shift_start']>=p['shift_end']:raise ValueError('人员班次倒置')
    return d
