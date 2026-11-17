"""Verify bundled data without accessing the internet or the original workspace."""
import argparse
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/public-benchmarks'

def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def check(entries,base):
    errors=[]
    for row in entries:
        relative=Path(row['path'].replace('\\','/'))
        path=(base/relative).resolve()
        if not path.is_relative_to(base.resolve()):
            errors.append({'path':str(relative),'error':'path outside bundle'});continue
        if not path.is_file():errors.append({'path':str(relative),'error':'missing file'});continue
        if sha256(path)!=row['sha256']:errors.append({'path':str(relative),'error':'SHA-256 mismatch'})
    return errors

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--full',action='store_true',help='also verify auxiliary networks, sources and licenses')
    parser.add_argument('--test',action='store_true',help='run the 12 public benchmark regression tests')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:
        entries=json.loads((DATA/'manifest.json').read_text('utf8'))['instances']
        errors=check(entries,ROOT);full=[]
        if args.full:
            full=json.loads((DATA/'bundle-files.json').read_text('utf8'))['files']
            errors+=check(full,DATA)
    except (OSError,KeyError,ValueError) as e:
        print('DATA CHECK FAILED: '+str(e));return 1
    result={'status':'passed' if not errors else 'failed','manifest_instances':len(entries),'auxiliary_files':len(full),'errors':errors,'data_root':str(DATA),'external_data_used':False}
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    if errors:return 1
    if args.test:
        sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'.vendor'))
        suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_public_benchmark.py')
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    return 0

if __name__=='__main__':sys.exit(main())
