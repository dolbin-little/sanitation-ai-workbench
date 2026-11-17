"""Streaming, compact storage of the unchanged author-provided TDSP functions.
No interpolation, quantization, breakpoint removal, or algorithm change.
"""
from array import array
import hashlib
from pathlib import Path

class Triples:
    def __init__(self,flat):self.flat=flat
    def __getitem__(self,k):
        if k<0:k+=len(self)
        i=k*3;return self.flat[i],self.flat[i+1],self.flat[i+2]
    def __len__(self):return len(self.flat)//3

def profile(tokens):
    flat=array('d',map(float,tokens));assert len(flat)%3==0
    xs=flat[::3]
    assert all(a<=b+1e-8 for a,b in zip(xs,xs[1:]))
    return xs,Triples(flat)

def read_td(path):
    path=Path(path);h={};service={};jobs=[None];travel={}
    sha=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
    with path.open(encoding='ascii') as f:
        for line in f:
            if line.strip()=='[REQUIRED_EDGES]':break
            if ':' in line:
                k,v=line.split(':',1);h[k.strip()]=v.strip()
        n=int(h['EDG_REQ'])
        lines=(line for line in f if line.strip())
        for i in range(1,n+1):
            a=next(lines).split();b=next(lines).split();u,v=int(a[0]),int(a[1])
            assert (int(b[0]),int(b[1]))==(v,u)
            jobs.append(dict(u=u,v=v,demand=float(a[3]),cost=float(a[2])))
            service[i]=profile(a[5:]);service[-i]=profile(b[5:])
        assert next(lines).strip()=='[NETWORK_DATA]'
        for line in lines:
            a=line.split();u,v,k=map(int,a[:3]);travel[u,v]=profile(a[3:]) if k else None
            assert k or u==v
    assert len(travel)==int(h['VERTICES'])**2
    return dict(name=path.stem,family='TDCARP-'+path.parent.name,kind='tdcarp',sha256=sha,
                capacity=float(h['CAPACITY']),vehicles=int(h['VEHICLES']),depot=int(h['DEPOT']),n=n,
                jobs=jobs,travel=travel,service=service,horizon=float(h['ENDTIME']),raw=str(path))
