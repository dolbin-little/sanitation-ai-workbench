"""Real-model file workflow using isolated synthetic data only."""
import sys,json,tempfile,uuid,base64,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import server
from assistant_service import Assistant
from assistant_files import extract
import openpyxl
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject

def main():
    records=[]
    with tempfile.TemporaryDirectory() as folder:
        store=server.fleet_server.Store(Path(folder)/'fleet.sqlite3');s=store.read();s['tasks']=s['tasks'][:3];s['vehicles']=s['vehicles'][:6];store.save(s);ai=Assistant(store)
        row=dict(id='LIVE-FILE-01',name='文件联调测试任务',kind='collection',start='N1-4',end='N1-4',earliest=420,deadline=600,service=8,demand=1,water=0,priority=3)
        workbook=openpyxl.Workbook();workbook.active.append(list(row));workbook.active.append(list(row.values()));stream=io.BytesIO();workbook.save(stream)
        file=extract({'filename':'tasks.xlsx','base64':base64.b64encode(stream.getvalue()).decode()})
        body=dict(session_id='files-'+uuid.uuid4().hex,request_id=str(uuid.uuid4()),revision=s['revision'],message='请把附件的任务导入，并生成候选方案，不要下发。',execute=True,attachment=file)
        out=ai.call('chat',body);after=store.read();records.append({'case':'XLSX提取→模型理解→导入→候选','passed':any(t['id']==row['id'] for t in after['tasks']) and after['draft'] is not None and after['plan'] is None,'answer':out['answer'],'results':out.get('results',[])})
        w=PdfWriter();page=w.add_blank_page(600,800);font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')});page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):w._add_object(font)})});data=DecodedStreamObject();data.set_data(b'BT /F1 20 Tf 50 700 Td (Vehicle V03 status FAULT) Tj ET');page[NameObject('/Contents')]=w._add_object(data);stream=io.BytesIO();w.write(stream)
        pdf=extract({'filename':'event.pdf','base64':base64.b64encode(stream.getvalue()).decode()})
        out=ai.call('chat',dict(session_id='pdf-'+uuid.uuid4().hex,request_id=str(uuid.uuid4()),revision=after['revision'],message='请根据PDF中明确的车辆编号和故障状态，登记车辆故障，不要下发。',execute=True,attachment=pdf));after=store.read();records.append({'case':'文字PDF提取→故障登记','passed':not next(v for v in after['vehicles'] if v['id']=='V03')['enabled'] and after['plan'] is None,'answer':out['answer'],'results':out.get('results',[])})
        out=ai.call('chat',dict(session_id='map-'+uuid.uuid4().hex,request_id=str(uuid.uuid4()),revision=after['revision'],message='帮我在地图左上角加一个垃圾收运任务，其他参数我暂时没有。',execute=True));records.append({'case':'地图位置不明确时不编造任务','passed':not out.get('results') and len(store.read()['tasks'])==4,'answer':out['answer']})
    (ROOT/'evidence/assistant_round2_files_live.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8');print('PASS',sum(r['passed'] for r in records),'/',len(records))
if __name__=='__main__':main()
