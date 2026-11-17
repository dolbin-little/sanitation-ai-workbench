"""Deterministic business-header normalization, explicit mappings and geographic checks."""
import hashlib,json,math,re

ALIASES={
 'id':['任务编号','工单编号','编号'], 'name':['任务名称','作业名称','名称'],
 'kind':['作业类型','任务类型','车型'], 'start':['作业地点','起点','收运点','地点','节点'],
 'end':['终点','作业终点'], 'earliest':['开始时间','最早时间','最早开始'],
 'deadline':['完成时限','截止时间','最晚完成'], 'service':['作业时长','服务时长','时长分钟'],
 'demand':['垃圾量','载重需求','需求吨数'], 'water':['用水量','水量'], 'priority':['优先级'],
 'locked_to':['车牌号','车牌','执行车辆','车辆编号'], 'longitude':['经度','lng','lon'], 'latitude':['纬度','lat'],
 'coordinate_system':['坐标系']}
FIELDS=list(ALIASES)
KINDS={'垃圾收运':'collection','收运':'collection','压缩收运车':'collection','道路洗扫':'sweeper','洗扫':'sweeper','道路洗扫车':'sweeper','箱体转运':'hook','勾臂车':'hook','勾臂运输车':'hook'}

def suggest(headers):
    return {f:next((h for h in headers if h.strip().lower() in [f]+[a.lower() for a in names]),'') for f,names in ALIASES.items()}

def minute(v):
    if isinstance(v,str) and re.fullmatch(r'\d{1,2}:\d{2}(?::00)?',v.strip()):
        parts=v.strip().split(':');h,m=int(parts[0]),int(parts[1])
        if h>23 or m>59:raise ValueError('时间须为00:00—23:59')
        return 60*h+m
    return v

def normalize(s,rows,options=None):
    if not isinstance(rows,list) or not 1<=len(rows)<=500 or any(not isinstance(r,dict) for r in rows):raise ValueError('须为1—500条任务对象')
    options=options or {};headers=list(dict.fromkeys(k for r in rows for k in r));mapping=suggest(headers)
    for f,h in options.get('mapping',{}).items():
        if f not in FIELDS or (h and h not in headers):raise ValueError('字段映射无效')
        mapping[f]=h
    defaults=options.get('defaults',{});places=options.get('locations',{})
    if not isinstance(defaults,dict) or not isinstance(places,dict):raise ValueError('补充参数格式错误')
    nodes={n['id']:n for n in s['nodes']};out=[];problems=[]
    for i,row in enumerate(rows):
        r={f:row[h] for f,h in mapping.items() if h and row.get(h) not in (None,'')}
        for f,v in defaults.items():
            if f in FIELDS and r.get(f) in (None,'') and v not in (None,''):r[f]=v
        r['id']=str(r.get('id') or 'IMP-'+hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:10])
        errors=[]
        if r.get('kind') in KINDS:r['kind']=KINDS[r['kind']]
        for f in ('earliest','deadline'):
            try:
                if f in r:r[f]=minute(r[f])
            except ValueError as e:errors.append(str(e))
        if r.get('locked_to'):
            v=[v for v in s['vehicles'] if str(r['locked_to']) in (v['id'],v.get('name'),v.get('plate'),v.get('license_plate'))]
            if len(v)!=1:errors.append('车牌/车辆无法唯一匹配现有车辆')
            else:
                r['locked_to']=v[0]['id'];r.setdefault('kind',v[0]['kind'])
                if r['kind']!=v[0]['kind'] or not v[0]['enabled']:errors.append('指定车辆车型不兼容或处于故障')
        for f in ('start','end'):
            if f in r:
                r[f]=places.get(str(r[f]),r[f])
                named=[n['id'] for n in s['nodes'] if n.get('name')==r[f]]
                if r[f] not in nodes and len(named)==1:r[f]=named[0]
        if r.get('longitude') is not None or r.get('latitude') is not None:
            try:
                lon,lat=float(r['longitude']),float(r['latitude'])
                if not math.isfinite(lon+lat) or not -180<=lon<=180 or not -90<=lat<=90:raise ValueError('经纬度范围无效')
                if r.get('coordinate_system')!='WGS84':raise ValueError('须明确WGS84坐标系，不能混用GCJ02/地图示意坐标')
                candidates=[]
                for n in s['nodes']:
                    if n.get('coordinate_system')=='WGS84' and 'longitude' in n and 'latitude' in n:
                        a,b=math.radians(lat),math.radians(float(n['latitude']));dlat=a-b;dlon=math.radians(lon-float(n['longitude']))
                        h=math.sin(dlat/2)**2+math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
                        distance=12742000*math.asin(math.sqrt(max(0,min(1,h))))
                        if distance<=30:candidates.append(n['id'])
                if len(candidates)!=1:raise ValueError('30米内没有唯一已配准节点；请提供地点→节点对应关系')
                if r.get('start') and r['start']!=candidates[0]:raise ValueError('地点节点与经纬度对应关系冲突')
                r['start']=candidates[0]
            except (KeyError,TypeError,ValueError) as e:errors.append('坐标匹配：'+str(e))
        if r.get('kind') in ('collection','hook') and r.get('start'):r.setdefault('end',r['start'])
        for f in ('start','end'):
            if r.get(f) and r[f] not in nodes:errors.append(f+'地点未映射到现有节点')
        missing=[f for f in ('name','kind','start','end','earliest','deadline','service','demand','water','priority') if r.get(f) in (None,'')]
        if missing:errors.append('请集中补充：'+','.join(missing))
        if errors:problems.append({'row':i+1,'id':r['id'],'missing':missing,'error':'；'.join(errors)})
        out.append(r)
    return out,problems,{'headers':headers,'mapping':mapping,'ignored':[h for h in headers if h not in mapping.values()]}
