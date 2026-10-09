"""Record the final frozen package tests, including real Blender installation."""
import os
os.environ["PYTHONIOENCODING"]="utf-8"
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
WORKSPACE=ROOT.parent
ARCHIVE=WORKSPACE/'batch_rename-1.4.0-blender51.zip'
LOGS=HERE/'audit_1.4.0_logs';LOGS.mkdir(exist_ok=True)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
with zipfile.ZipFile(ARCHIVE) as z:
    assert z.testzip() is None
    for name in z.namelist():assert z.read(name)==(ROOT/name).read_bytes()
    sources={name:digest(ROOT/name) for name in z.namelist()}
report={'version':'1.4.0','archive':ARCHIVE.name,'sha256':digest(ARCHIVE),'source_sha256':sources,
    'rounds':['All source files reviewed for registration, lifecycle and packaging',
              'Functional and persistence review with reproduced edge cases',
              'Frozen ZIP installation and full regression on real bpy 5.1.0 and 5.2.2'],
    'limits':['Uses official Windows bpy runtimes and the real extension Install from Disk backend',
              'Interactive GUI pixel rendering was not tested',
              'Undo/redo synchronization handler tested with real RNA; interactive undo stack unavailable in background bpy'],
    'tests':[]}
jobs=[('offline',sys.executable,'test_offline.py',[], 'Ran 18 tests'),
      ('data_edges',sys.executable,'test_data_edges.py',[],'Ran 13 tests')]
for runtime in ('bpy51','bpy52'):
    exe=str(WORKSPACE/'blender_validation_runtime'/runtime/'python.exe')
    jobs.extend([
        (runtime+'_install',exe,'blender_install.py',[str(ARCHIVE)],'WKNGR REAL INSTALLATION PASS:'),
        (runtime+'_upgrade_original',exe,'blender_install.py',['--upgrade-original',str(ARCHIVE)],'ORIGINAL FAILURE TO FIXED UPGRADE PASS'),
        (runtime+'_upgrade_previous',exe,'blender_install.py',['--upgrade-previous',str(ARCHIVE)],'WKNGR REAL INSTALLATION PASS:'),
        (runtime+'_smoke',exe,'blender_smoke.py',[],'WKNGR REAL BLENDER SMOKE PASS:'),
        (runtime+'_functional',exe,'blender_functional.py',[],'Ran 51 tests')])
for name,exe,script,args,marker in jobs:
    started=time.monotonic()
    result=subprocess.run([exe,str(HERE/script),*args],cwd=WORKSPACE,stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,timeout=120)
    output=result.stdout.decode('utf-8',errors='replace')
    (LOGS/(name+'.log')).write_text(output,encoding='utf-8')
    passed=result.returncode==0 and marker in output and 'ModuleNotFoundError' not in output
    report['tests'].append({'name':name,'passed':passed,'exit_code':result.returncode,
        'seconds':round(time.monotonic()-started,2),'log':'audit_1.4.0_logs/'+name+'.log'})
    (HERE/'audit_1.4.0_result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(name,'PASS' if passed else 'FAIL',report['tests'][-1]['seconds'],flush=True)
    if not passed:
        print(output,flush=True)
        raise SystemExit(1)
assert digest(ARCHIVE)==report['sha256']
for name,expected in sources.items():assert digest(ROOT/name)==expected
report['all_passed']=True
(HERE/'audit_1.4.0_result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('FINAL AUDIT ALL PASS',report['sha256'],flush=True)
