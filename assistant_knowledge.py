"""Local lexical retrieval over explicit project sources, with inspectable citations."""
import json, math, re, hashlib
from pathlib import Path
from collections import Counter

def tokens(text):
    words=re.findall(r'[a-zA-Z_][a-zA-Z_0-9-]*',text.lower())
    for run in re.findall(r'[\u4e00-\u9fff]+',text):
        words.extend(run[i:i+2] for i in range(len(run)-1))
        if len(run)==1:words.append(run)
    return words

class Knowledge:
    def __init__(self,root):
        self.root=Path(root);self.chunks=[]
        files=['assistant_knowledge/操作指南.txt','assistant_knowledge/资料范围.txt',
               'legacy/backend/service.py','legacy/backend/model.py','legacy/backend/control.py',
               'legacy/backend/shield.py','legacy/backend/optimizer.py','legacy/backend/risk.py',
               'drive/edge.py','drive/session.py']
        for name in files:
            p=self.root/name
            if not p.exists():continue
            lines=p.read_text('utf-8-sig').splitlines()
            for start in range(0,len(lines),24):
                self.add(name+f':L{start+1}', '\n'.join(lines[start:start+30]), '本地实现' if p.suffix=='.py' else '操作说明')
        for p in sorted((self.root/'references').glob('*/source_registry.json')):
            registry=json.loads(p.read_text('utf-8-sig'))
            rows=registry.get('sources',[])
            if isinstance(rows,dict):rows=list(rows.values())
            for row in rows:
                if not isinstance(row,dict):continue
                keep={k:row[k] for k in ('id','title','doi','urls','original_method','adaptation','implementation','use_status','must_not_claim','scope','limitations') if k in row}
                self.add(str(p.relative_to(self.root)).replace('\\','/')+'#'+str(row.get('id',len(self.chunks))),json.dumps(keep,ensure_ascii=False),'来源登记（非论文全文）')
        for c in self.chunks:c['tf']=Counter(tokens(c['text']+' '+c['source']))
        self.df=Counter(t for c in self.chunks for t in c['tf']);self.avg=sum(sum(c['tf'].values()) for c in self.chunks)/max(1,len(self.chunks))
    def add(self,source,body,kind):
        if not body.strip():return
        self.chunks.append({'id':'K-'+hashlib.sha256(source.encode()).hexdigest()[:10],'source':source,'text':body[:5000],'kind':kind})
    def search(self,q,limit=5):
        query=set(tokens(q));rank=[];n=len(self.chunks)
        for c in self.chunks:
            length=sum(c['tf'].values());score=0
            for t in query:
                f=c['tf'][t]
                if f:score+=math.log(1+(n-self.df[t]+.5)/(self.df[t]+.5))*f*2.2/(f+1.2*(.25+.75*length/max(1,self.avg)))
            if score>0:rank.append((score,c))
        return [{k:c[k] for k in ('id','source','text','kind')} for _,c in sorted(rank,key=lambda pair:-pair[0])[:limit]]
    def summary(self):
        return {'chunks':len(self.chunks),'sources':len({c['source'].split(':L')[0] for c in self.chunks}),'method':'本地BM25关键词检索；不训练模型、不上传完整资料库','documents':sorted({c['source'].split(':L')[0] for c in self.chunks})}
