"""Inventory downloaded original archives, unpack TDSP, snapshot BKS, SHA256 manifest."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import backend
import hashlib,json,re,datetime
from html import unescape
import py7zr
from backend.public_benchmark import read_instance
from backend.public_td_compact import read_td
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data/public-benchmarks'

def main():
    # Keep the BKS snapshot bound to the archived page, never fetch fresh values
    # halfway through an existing experiment.
    if not (DATA/'solomon-bks.json').exists():
        page=(DATA/'solomon-bks.html').read_text(encoding='utf-8');bks={}
        for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',page,re.S|re.I):
            cells=[unescape(re.sub('<[^>]+>',' ',c)).strip() for c in re.findall(r'<td\b[^>]*>(.*?)</td>',row,re.S|re.I)]
            if len(cells)>2 and re.fullmatch(r'(?:c|r|rc)\d{3}b?',cells[0],re.I):
                bks[cells[0].lower().removesuffix('b')]={'vehicles':int(cells[1]),'distance':float(cells[2].replace('*',''))}
        assert len(bks)==56
        (DATA/'solomon-bks.json').write_text(json.dumps({'source':'https://www.sintef.no/projectweb/top/vrptw/100-customers/','values':bks},indent=2))
    for archive in DATA.rglob('*.7z'):
        with py7zr.SevenZipFile(archive) as z:
            names=z.getnames()
            if not all((archive.parent/n).exists() for n in names):z.extractall(archive.parent)
    paths=sorted((DATA/'solomon').rglob('*.txt'))
    for family in ('gdb','bccm','eglese','kshs'):paths+=sorted((DATA/family).rglob('*.dat'))
    paths+=sorted((DATA/'tdcarp').rglob('*.tdsp'))
    rows=[]
    for path in paths:
        p=(read_td if path.suffix=='.tdsp' else read_instance)(path)
        rows.append({k:p[k] for k in ('name','family','kind','sha256','n','vehicles','capacity')}
                    |{'path':str(path.relative_to(ROOT))})
    assert len(rows)==203,(len(rows),'unexpected source manifest')
    assert len({(r['family'],r['name']) for r in rows})==203
    archives=[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
              for p in sorted(DATA.glob('*.zip'))]
    manifest={'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'instances':rows,'archives':archives,
              'sources':json.loads((DATA/'sources.json').read_text(encoding='utf-8-sig'))}
    if (DATA/'manifest.json').exists():
        old=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
        if old['instances']==rows and old['archives']==archives:
            print('manifest unchanged',len(rows),flush=True);return
    (DATA/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('manifest',len(rows),flush=True)

if __name__=='__main__':main()
