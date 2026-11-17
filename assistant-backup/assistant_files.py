"""Bounded local extraction. Does not execute spreadsheets/macros or embedded files."""
import base64, io, json, sys, zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'assistant_vendor'))

def extract(body):
    name=str(body.get('filename',''));ext=Path(name).suffix.lower()
    try:data=base64.b64decode(body.get('base64',''),validate=True)
    except (ValueError,TypeError):raise ValueError('无效文件编码')
    if not 0<len(data)<=2000000:raise ValueError('文件上限2MB')
    if ext=='.xlsx':
        import openpyxl
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist())>20000000 or len(z.infolist())>1000:raise ValueError('工作簿解压尺寸过大')
        wb=openpyxl.load_workbook(io.BytesIO(data),read_only=True,data_only=False)
        try:
            ws=wb.worksheets[0];rows=ws.iter_rows(values_only=True);headers=next(rows,())
            if len(headers)>40:raise ValueError('最多40列')
            headers=[str(h).strip() if h is not None else '' for h in headers]
            if len(headers)!=len(set(headers)):raise ValueError('首行字段重复')
            out=[]
            for row in rows:
                if not any(v is not None for v in row):continue
                if len(out)>=500:raise ValueError('单次最多500条任务')
                if any(isinstance(v,str) and v.startswith('=') for v in row):raise ValueError('请把公式转换为实际数值后再导入')
                out.append({k:v for k,v in zip(headers,row) if k})
            return {'filename':Path(name).stem+'.json','content':json.dumps(out,ensure_ascii=False,default=str),'kind':'tasks','note':'已读取首个工作表；其他工作表未导入'}
        finally:wb.close()
    if ext=='.pdf':
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(data))
        if reader.is_encrypted:raise ValueError('请提供未加密PDF')
        if len(reader.pages)>30:raise ValueError('单次PDF最多30页')
        parts=[]
        for i,page in enumerate(reader.pages):
            parts.append(f'第{i+1}页\n'+(page.extract_text() or ''))
            if sum(map(len,parts))>60000:raise ValueError('PDF文字过多，请分段上传')
        if not ''.join(p.extract_text() or '' for p in reader.pages).strip():raise ValueError('PDF没有可提取文字；请提供清晰图片，或转为文字清单')
        return {'filename':name+'.txt','content':'\n\n'.join(parts),'kind':'text','note':'PDF提取文字将发送给模型理解；尚未导入业务任务'}
    raise ValueError('此接口支持XLSX与文字PDF')
