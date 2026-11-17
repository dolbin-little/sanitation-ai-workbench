"""Build the anonymous AIC eight-section technical report from measured artifacts."""
import json,hashlib
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,Table,TableStyle,Image,KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor,white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT
ROOT=Path(__file__).resolve().parents[1]
pdfmetrics.registerFont(TTFont('CN','C:/Windows/Fonts/msyh.ttc',subfontIndex=0))
pdfmetrics.registerFont(TTFont('CNB','C:/Windows/Fonts/msyhbd.ttc',subfontIndex=0))
styles={
 'title':ParagraphStyle('title',fontName='CNB',fontSize=26,leading=39,textColor=HexColor('#173c52'),spaceAfter=20),
 'h1':ParagraphStyle('h1',fontName='CNB',fontSize=19,leading=28,textColor=HexColor('#173c52'),spaceAfter=18),
 'h2':ParagraphStyle('h2',fontName='CNB',fontSize=12,leading=20,textColor=HexColor('#218a79'),spaceBefore=10,spaceAfter=7),
 'body':ParagraphStyle('body',fontName='CN',fontSize=10,leading=17,textColor=HexColor('#375569'),spaceAfter=10,wordWrap='CJK'),
 'small':ParagraphStyle('small',fontName='CN',fontSize=8,leading=12,textColor=HexColor('#6a8191'),spaceAfter=7,wordWrap='CJK'),
 'cell':ParagraphStyle('cell',fontName='CN',fontSize=8,leading=13,textColor=HexColor('#375569'),wordWrap='CJK'),
 'eyebrow':ParagraphStyle('eyebrow',fontName='CNB',fontSize=9,leading=17,textColor=HexColor('#238e7a'),spaceAfter=16)}
story=[]
def p(t,style='body'):return Paragraph(t,styles[style])
def add(t,style='body'):story.append(p(t,style))
def section(num,title):
 story.append(PageBreak());add('TECHNICAL REPORT / '+str(num).zfill(2),'eyebrow');add(title,'h1')
def table(headers,rows,widths):
 values=[[p(escape(str(x)),'cell') for x in headers]]+[[p(escape(str(x)),'cell') for x in row] for row in rows]
 t=Table(values,colWidths=widths,repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#e8f2f5')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),('LINEBELOW',(0,0),(-1,-1),.4,HexColor('#dbe7ee')),('ROWBACKGROUNDS',(0,1),(-1,-1),[white,HexColor('#f8fbfc')])]))
 story.append(t);story.append(Spacer(1,10))
def footer(c,d):
 c.saveState();w,h=d.pagesize;c.setStrokeColor(HexColor('#dbe8ee'));c.line(42,42,w-42,42);c.setFont('CN',8);c.setFillColor(HexColor('#8194a1'));c.drawString(42,27,'环卫智枢 / 低速作业驾驶协同 / 二维研究仿真');c.drawRightString(w-42,27,str(d.page));c.restoreState()
def main():
 summary=json.loads((ROOT/'evidence/summary.json').read_text('utf-8'));training=json.loads((ROOT/'evidence/bc_training.json').read_text('utf-8'));totalmap={r['policy']:r for r in summary['totals']}
 add('2026 AIC · 智能驾驶算法主题赛','eyebrow');story.append(Spacer(1,35));add('环卫智枢<br/>低速作业驾驶协同','title');add('技术报告 · 匿名评阅版','h2');add('从车队工单到单车执行，再回到可复核的作业回执。')
 table(['成果定位','本版证据'],[['低速清扫与收运作业研究平台','6个新页面，保留车队调度与任务中心'],['感知 - 规划 - 控制 - 安全闭环','9类合成场景、10个测试种子、4种策略，共360回合'],['可复核学习与故障试验','实际训练的18维行为克隆基线、独立安全监控、原始CSV和回放']], [190,320])
 image=ROOT/'evidence/驾驶舱.jpg'
 if image.exists():
  from PIL import Image as PI
  with PI.open(image) as im:w,h=im.size
  ratio=min(510/w,260/h);story.append(Image(str(image),width=w*ratio,height=h*ratio))
 add('版本：1.0.0-aic-sanitation-sim　｜　完成日期：2026年10月30日','small')
 add('研究范围：独立二维服务道路。未接入实车、真实相机或V2X设备；未运行预训练自动驾驶基础模型，不主张功能安全认证。','small')

 section(1,'一、作品背景与目标定位')
 add('1.1 政策与行业背景','h2')
 add('五部门关于开展智能网联汽车“车路云一体化”应用试点工作的通知明确了2024-2026年试点方向，推动车、路、网、云、图协同与多场景应用、测试评价体系建设[1]。本作品以此为应用背景，选择环卫低速作业这一具体场景。政策方向不等于本项目获得试点资质或商业落地证明。')
 add('既有环卫平台解决多车辆任务分配、资源约束和异常后重新安排；工单被分给车辆以后，靠站、绕行、行人礼让和故障停车仍需要执行层解释。单看优化里程与任务完成表，难以核对单车遇到环境变化后的实际行为。')
 add('1.2 本版目标','h2')
 add('围绕清扫与收运工单，增加可运行、可解释、可回放的单车驾驶研究闭环。目标是在同一平台观察“任务交给谁、车辆看到什么、怎样选择轨迹、为什么制动、是否完成作业”，并用配对试验检验策略差异。')
 table(['环卫作业','驾驶层目标'],[['定点垃圾收运','低速抵达目标并连续停车驻留3秒'],['道路连续清扫','1.8m/s限速，在指定服务带记录覆盖单元'],['突发环境与设备故障','行人让行、违停绕行、封路改道、红灯保护、感知陈旧停车、链路退化降级']], [135,375])
 add('不设虚构经济指标。该成果当前用于算法验证与演示；真实节省成本、能耗、投诉率等须由现场数据验证。','small')

 section(2,'二、需求分析与应用场景')
 add('2.1 问题分解','h2')
 add('问题一：车队层分配与执行层脱节。保留原任务中心，从当前车队快照关联工单和车辆；无确认分配时仅给出车型兼容的仿真建议，并明确标识。')
 add('问题二：驾驶建议不可解释。地图同时展示全局路线、候选局部轨迹、跟踪目标和实际轨迹，安全卡片展示感知年龄、间距与制动原因；允许人工接管和急停。')
 add('问题三：成功演示不足以证明稳定。对每类场景固定测试种子、策略和指标；接触终止、超时不完成等都进入原始结果。')
 add('2.2 需求来源与约束','h2')
 add('本版需求来自既有平台的工单流程、页面使用反馈、提交的赛题附件与公开论文分析；没有将拟采访单位写为已经访谈或合作的客户，也没有虚构实车数据。')
 table(['具体要求','实现与验收'],[['可运行','自带Python 3.12，start.cmd启动本地8780端口'],['可解释、可干预','6页工作台、15候选轨迹表、人工转角/加速度、急停'],['可核查','SQLite模拟回执、CSV逐回合指标、冻结协议和权重哈希'],['保持环卫边界','清扫覆盖、收运驻留、车队工单关联；不扩展泛用座舱娱乐或低空控制']], [130,380])
 add('本版以100×70米抽象服务道路替代真实路网；原车队分钟级时钟与驾驶秒级时钟独立，不能拼接为实车调度耗时。','small')

 section(3,'三、整体技术方案与架构')
 table(['层次','库 / 架构 / 数据'],[['网页交互','原生HTML、CSS、JavaScript与Canvas；本地HTTP JSON，无前端构建依赖'],['服务与存储','Python ThreadingHTTPServer；继承原车队Handler；DriveStore独立状态锁与版本；SQLite持久化回执'],['感知与规划','标准库实现射线求交、聚类、α-β跟踪、A*、Pure Pursuit与局部轨迹采样'],['学习与推理','NumPy训练MLP；JSON权重；在线推理采用纯Python，CPU可运行'],['车队基础','复制保留原backend、web、数据与依赖，继续提供H-ALNS等调度能力；本版未以驾驶测试替代其原约束验收']], [100,410])
 add('执行数据流','h2');add('环卫工单快照 → 场景加载 → 虚拟雷达与信号观测 → 聚类和跟踪 → A*全局路径 → 速度/转角采样 → 独立安全检查 → 运动学车辆推进 → 作业指标与模拟回执。')
 add('环境真值只用于传感器生成、物理积分、评估与可关闭的调试图层。驾驶控制接收自车定位、观测目标、地图和合成信号/V2X消息；不把环境真值ID直接输入规划器。')
 add('接口与一致性','h2');add('驾驶接口位于/api/drive/，原车队接口保持/api/。修改请求检查本地Origin、JSON大小、有限数值和状态revision；过期请求拒绝。驾驶回执不会扣减车队资源或把待执行工单改成实车完成。')

 section(4,'四、关键技术与创新实现')
 add('4.1 感知、规划与控制','h2')
 add('96束平面射线、24m量程，与圆形物体求交并加设定噪声；相邻聚类后以最近邻和α-β滤波维护目标。类别与评分为几何启发，不等于训练出的真实行人检测器。')
 add('A*在2m栅格搜索，检查障碍膨胀与对角通行。Pure Pursuit生成参考转角，局部采样5个转角偏移×3档速度，按进度、路径误差、净间距与道路足迹筛选。纵向采用P速度控制。本实现借鉴DWA思想并适配自行车模型，未声称完整复现DWA。')
 add('独立安全检查对拟执行指令再次前向模拟，检查感知陈旧、红灯与观测净间距。停车距离近似为v×0.4+v²/(2×2)+1米，制动能力为设定假设。车辆采用后轴参考、2.8m轴距、4.2m车长、1.8m车宽及转向速率限制。')
 add('4.2 学习与边缘协同','h2')
 add('行为克隆以雷达分区距离、自车状态、导航、信号与作业限速共18维特征预测转角和加速度。18→32→16→2 MLP经NumPy/Adam训练，输入含Pure Pursuit建议转角，是带人工导航特征的模仿基线；不是图像端到端或预训练驾驶基础模型。外部模型适配器只回放带来源的航点记录。')
 add('借鉴优先级卸载论文[5]区分关键本地控制与可选计算，利用非抢占优先级M/G/1估计均值等待；借鉴资源优化子问题[6]采用平方根分配；借鉴专利[7]的“先时延约束后配置偏好”原则选择设定传感配置。三者均为局部独立改编，未复现原文全算法或专利检测器。')
 add('4.3 本项目组合贡献','h2');add('以环卫工单贯通任务、驾驶与模拟回执；将低速清扫覆盖、靠站驻留、车端安全与边缘可选计算放进同一可解释界面；按冻结协议保留故障与失败证据。基础算法是公开已有方法，不作为独创算法或他人专利所有权申报。')

 section(5,'五、项目实施与测试验证')
 add('5.1 实施与复现条件','h2');add('先复制既有平台并隔离数据库，再实现感知/驾驶闭环、界面与边缘模型；训练权重后冻结测试协议，运行配对评估与功能测试。新增工程由AI辅助实现与检查，参赛成员须按实际审阅、开发和测试工作说明贡献。')
 add('训练：9类场景×种子0-7共72段教师回合，隔帧采样'+str(training['train']['samples'])+'条；验证：种子80-81共18回合、'+str(training['validation']['samples'])+'条。归一化仅拟合训练集；150轮Adam，学习率0.003，训练随机种子42。验证归一化动作MAE为'+f"{training['validation']['normalized_action_mae']:.4f}"+'。测试种子1000-1009不参与训练。')
 add('5.2 冻结试验与指标','h2');add('9类场景×10种子×4策略=360回合。控制周期0.2s，真值评价子步0.05s，上限110s。无违规作业成功要求完成到点驻留且无接触、无道路足迹越界、无红灯越线；未完成与失败均纳入分母。')
 names={'reactive':'固定路径反应制动','shielded':'环卫规划＋安全','no_shield':'规划关闭安全','bc_guarded':'行为克隆＋安全'}
 table(['策略','n','无违规成功','接触回合','越界回合','闯红灯回合'],[[names[r['policy']],r['n'],r['safe_success'],r['collision_episodes'],r['offroad_episodes'],r['red_episodes']] for r in summary['totals']],[145,35,90,80,80,80])
 add('规划＋安全有'+str(totalmap['shielded']['safe_success'])+'/90回合达到无违规作业成功，接触回合为'+str(totalmap['shielded']['collision_episodes'])+'；只支持本生成器范围。关闭安全的接触回合为'+str(totalmap['no_shield']['collision_episodes'])+'。行为克隆为'+str(totalmap['bc_guarded']['safe_success'])+'/90，继续保留为研究对照。清扫覆盖不足、超时与所有违规均保留在原始结果。本组开启与关闭独立安全监控的总成功率相同，不能据此声称安全层提高成功率；其作用以陈旧等触发记录说明。固定路径基线能力较弱，不能据此推断优于成熟自动驾驶系统。')
 add('记录每组Wilson95%区间，逐回合明细与失败回放在evidence/。CPU耗时包含传感器、规划、控制、保护和真值评估，四进程并行有竞争，不能当作实车控制实时性或单独策略推理速度；各策略均运行教师规划以统一记录。14项功能/接口测试通过。','small')

 section(6,'六、成果展示与应用价值')
 table(['页面','实际展示与操作'],[['环卫驾驶舱','工单、仿真建议/确认快照车辆、路径、目标、速度、保护原因、急停'],['环境感知','雷达点、跟踪目标、估计速度与观测年龄'],['决策与车辆控制','15组候选、最终转角/加速度、曲线、人工接管'],['车端与边缘协同','关键本地任务、可选卸载、预算分配、设定时延门控'],['场景测试与回执','360回合结果、独立持久化工单模拟回执'],['模型与技术溯源','实际BC权重状态、轨迹记录适配器、引用与采用范围']], [130,380])
 add('直接价值','h2');add('让环卫调度人员从一张任务表深入核对单车遇到障碍后的行为；为学生和研发团队提供可解释、可干预的低速作业测试环境；以同种子配对比较减少只展示成功案例的偏差。')
 add('现阶段证据','h2');add('已交付可运行本地程序、完整源码、已训练权重、使用说明、来源记录与原始试验文件。工单模拟回执可跨重启查看；原车队功能可从同一服务进入。')
 add('尚未获得现场用户试用、真实车载硬件/网络时延、实际清洁质量、能耗或运营成本数据，因此不填写节约百分比、商业收入或客户合作证明。','small')

 section(7,'七、总结、局限与后续计划')
 add('已完成与保留','h2');add('保留原车队任务与调度流程，在独立目录增加低速环卫驾驶闭环、解释界面、人工干预、边缘计算模型与配对测试。将“作业到点完成”与“无违规作业成功”区分，公开未完成回合和学习基线不足。')
 add('主要局限','h2');add('环境为二维圆形对象和规则道路，不含三维遮挡、雨雾、复杂路权、相机图像和真实交通参与者意图。道路足迹以离散采样检查，50ms物理子步也不是严格连续碰撞证明。感知评估是“射线命中对象邻近关联率”的宽松代理，同一跟踪可能邻近多个目标，并非公开检测数据集mAP。')
 add('安全监控采用设定制动能力和短时运动预测，无法覆盖未建模故障、未知延迟或传感器系统误差。制动衰减未提前提供给控制器，不能以少量无接触回合推断故障安全性。清扫覆盖只是路线几何与速度代理，不等于垃圾清除率。')
 add('边缘页是卸载决策模型，没有真实服务器接收任务；配置时延是设定值，当前传感器仍固定96束。行为克隆不足以替代默认规划控制；外部轨迹接口不构成基础模型落地。')
 add('下一阶段','h2');add('先修复并回归两个超时案例，扩大道路、时机与速度分布；通过独立环境或公开驾驶数据检验泛化。随后在合法封闭场地接入硬件在环与真实传感器，测定通信/制动参数，并由业务单位验证清扫覆盖与靠站规则。现场试验和上路条件另行按适用要求办理。')

 section(8,'八、附录：代码、数据与参考来源')
 add('8.1 文件与复现命令','h2');add('运行：runtime/python.exe server.py --port 8780；测试：runtime/python.exe -m unittest discover -s tests -v；训练：runtime/python.exe scripts/train_bc.py；评估：runtime/python.exe scripts/evaluate.py。详见README.txt与docs/平台使用说明.txt。','small')
 add('原始数据：evidence/runs.csv；冻结协议：protocol.json；汇总与置信区间：summary.json；教师/验证记录：bc_training.json；代表回放：replays/。权重SHA256：'+summary['weights_sha256'],'small')
 add('8.2 主要来源与采用说明','h2')
 refs=[
 '[1] 工业和信息化部等五部门. 关于开展智能网联汽车“车路云一体化”应用试点工作的通知. 2024. miit.gov.cn；原始链接见references/policy.json。',
 '[2] Hart P E, Nilsson N J, Raphael B. A Formal Basis for the Heuristic Determination of Minimum Cost Paths. 1968. DOI:10.1109/TSSC.1968.300136. A*独立实现。',
 '[3] Fox D, Burgard W, Thrun S. The Dynamic Window Approach to Collision Avoidance. 1997. DOI:10.1109/100.580977. 仅借鉴局部采样思想。',
 '[4] Coulter R C. Implementation of the Pure Pursuit Path Tracking Algorithm. CMU-RI-TR-92-01,1992. 路径跟踪方法。',
 '[5] He Z, Xu Y, Zhao M, et al. Priority-Based Offloading Optimization in Cloud-Edge Collaborative Computing. IEEE TSC,2023. DOI:10.1109/TSC.2023.3296601. 任务分类与排队局部改编。',
 '[6] He Z, et al. Joint Computation Offloading and Resource Allocation in Mobile-Edge Cloud Computing: A Two-Layer Game Approach. IEEE TCC,2025. DOI:10.1109/TCC.2025.3538090. 仅采用固定卸载的资源子问题。',
 '[7] 基于边缘设备的目标检测方法. CN114612825B，申请号2022102309599. 仅借鉴时限配置筛选原则，不附他人证书为自有成果。',
 '[8] Shalev-Shwartz S, Shammah S, Shashua A. On a Formal Model of Safe and Scalable Self-driving Cars. arXiv:1708.06374. 显式制动距离思想参考，非完整RSS。',
 '[9] Pomerleau D A. ALVINN: An Autonomous Land Vehicle in a Neural Network. NeurIPS,1988. 学习控制背景；未复制图像网络。',
 '[10] AIC智能驾驶竞赛规则及作品提交要求；AIC智能驾驶技术报告参考大纲. 2026. 按提交附件核对。']
 for x in refs:add(escape(x),'small')
 add('全部来源、许可状态和代码采用位置见references/；本包不重新分发论文全文、导师简历或证书。既有开源依赖保留随包许可文件。','small')
 doc=SimpleDocTemplate(str(ROOT/'deliverables/技术报告.pdf'),pagesize=(595.28,841.89),rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=58,title='环卫智枢：低速作业驾驶协同',author='匿名参赛团队',pageCompression=1)
 doc.build(story,onFirstPage=footer,onLaterPages=footer)
 print('created',ROOT/'deliverables/技术报告.pdf')
if __name__=='__main__':main()
