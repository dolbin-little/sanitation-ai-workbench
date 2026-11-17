"""Temporary isolated browser acceptance server. No test endpoints in production."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import server
folder=ROOT/'evidence/round3_browser';folder.mkdir(exist_ok=True)
fleet=server.fleet_server.Store(folder/'fleet.sqlite3')
s=fleet.read()
if len(s['tasks'])==120 and s['revision']==1:
    s['tasks']=s['tasks'][:3];s['vehicles']=s['vehicles'][:6];s['settings']={'iterations':8,'budget':3};fleet.save(s)
drive=server.DriveStore(folder/'drive.sqlite3',fleet)
http=server.LocalHTTPServer(('127.0.0.1',18785),server.handler(fleet,drive))
print('Isolated acceptance http://127.0.0.1:18785',flush=True)
http.serve_forever()
