"""Create an additive portable archive, with a manifest and consistent SQLite backups."""
from pathlib import Path
import zipfile,hashlib,json,sqlite3,tempfile
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1]
def main():
    files=[]
    for p in ROOT.rglob('*'):
        if not p.is_file() or '__pycache__' in p.parts or p.suffix in ('.pyc','.log') or p.name.startswith('报告检查'):continue
        if p.name=='交付清单.json':continue
        files.append(p)
    out=ROOT.parent/'环卫智枢_智能驾驶版_可运行交付.zip'
    manifest={'project':'环卫智枢：低速作业驾驶协同','scope':'new independent folder; original source not edited','archive_name':out.name,'files':[]}
    with tempfile.TemporaryDirectory() as tmp:
        copies={}
        for p in files:
            if p.suffix=='.sqlite3':
                backup=Path(tmp)/(str(len(copies))+'.sqlite3')
                with closing(sqlite3.connect(str(p))) as src,closing(sqlite3.connect(str(backup))) as dst:src.backup(dst)
                copies[p]=backup
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=5) as z:
            for p in files:
                actual=copies.get(p,p);rel=p.relative_to(ROOT).as_posix();digest=hashlib.sha256(actual.read_bytes()).hexdigest()
                z.write(actual,ROOT.name+'/'+rel);manifest['files'].append({'path':rel,'bytes':actual.stat().st_size,'sha256':digest})
            text=json.dumps(manifest,ensure_ascii=False,indent=2);z.writestr(ROOT.name+'/交付清单.json',text)
        (ROOT/'交付清单.json').write_text(text,encoding='utf-8')
    with zipfile.ZipFile(out) as z:
        bad=z.testzip()
        if bad:raise RuntimeError('ZIP CRC failure: '+bad)
    result={'path':str(out),'bytes':out.stat().st_size,'files':len(files)+1,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'crc':'all_passed'}
    (ROOT/'evidence/package-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
