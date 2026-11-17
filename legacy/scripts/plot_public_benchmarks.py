"""Publication-exportable plots from actual saved benchmark rows; no inferred successes."""
import json,sys
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import backend
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
OUT=ROOT/'data/public-benchmarks/results/native-v1'
raw=[r for p in sorted(OUT.glob('*--*.json')) for r in json.loads(p.read_text())]
methods=['nearest','insertion','static_alns','adaptive_alns'];families=sorted({r['family'] for r in raw})
counts=defaultdict(Counter)
for r in raw:
    c=r.get('check',{});errors=c.get('errors',[])
    category=('Exception' if r['status']=='error' else 'Hard constraint' if any(e!='cost_mismatch' for e in errors)
              else 'Unserved tasks' if c.get('unassigned') else 'Cost mismatch' if errors else 'Verified complete')
    counts[r['family'],r['method']][category]+=1
categories=['Verified complete','Unserved tasks','Cost mismatch','Hard constraint','Exception']
colors=['#168775','#f4ba57','#c97a41','#b63a46','#61436f']
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
font=Path('C:/Windows/Fonts/msyh.ttc')
if font.exists():
    font_manager.fontManager.addfont(str(font));plt.rcParams['font.family']=font_manager.FontProperties(fname=str(font)).get_name()
fig,axs=plt.subplots(2,4,figsize=(15,7),sharey=True)
for ax,family in zip(axs.flat,families):
    bottom=np.zeros(4)
    for category,color in zip(categories,colors):
        values=np.array([100*counts[family,m][category]/sum(counts[family,m].values()) for m in methods])
        ax.bar(np.arange(4),values,bottom=bottom,color=color,label=category,width=.65);bottom+=values
    ax.set_title(f"{family} | {sum(counts[family,methods[0]].values())//30} instances");ax.set_xticks(range(4),['Nearest','Insert','Static','Adaptive'],rotation=25)
    ax.set_ylim(0,102);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
for ax in axs[:,0]:ax.set_ylabel('Share of runs (%)')
for ax in list(axs.flat)[len(families):]:ax.axis('off')
handles,labels=axs.flat[0].get_legend_handles_labels();fig.legend(handles,['完整且验算通过','存在未服务任务','成本验算不一致','约束/记账错误','程序异常'],loc='lower center',ncol=5,frameon=False)
complete=(OUT/'COMPLETE.json').exists()
fig.suptitle(f'公开基准原生轨道 · {len(raw):,} 次运行 · {"已完成" if complete else "运行中"}',fontsize=17,x=.05,ha='left')
fig.text(.05,.925,'每实例 30 个配对种子；搜索预算 2 秒 CPU / 200 次迭代；初解构造可能超时，失败全部保留。',color='#52646a')
fig.tight_layout(rect=(0,.08,1,.90))
for ext in ('png','svg','pdf'):fig.savefig(OUT/f'feasibility.{ext}',dpi=180,bbox_inches='tight')
plt.close(fig)
print('plots',len(raw),'runs')
