"""Run every test module in a separate process in an explicitly isolated clone."""
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


root=Path.cwd().resolve()
assert root.name=='clone' and root.parent.name=='claridad-implementacion'
output=root.parent/'regresion';output.mkdir(exist_ok=True)
isolated=output/'profile';isolated.mkdir(exist_ok=True)
env=os.environ.copy()
env.pop('VALENZA_RECEIPT_TEST_PDF',None)
env.update(PYTHONPATH=str(root/'src'),QT_QPA_PLATFORM='offscreen:configfile=../offscreen.json',
    USERPROFILE=str(isolated),LOCALAPPDATA=str(isolated/'Local'),APPDATA=str(isolated/'Roaming'))
results=[]
for module in sorted((root/'tests').glob('test_*.py')):
    name=module.stem
    xml=output/(name+'.xml')
    command=[sys.executable,'-m','pytest',str(module),'-q','-p','no:cacheprovider',
        '--basetemp='+str(output/(name+'-tmp')),'--junitxml='+str(xml)]
    with (output/(name+'.log')).open('w',encoding='utf-8') as log:
        try:
            result=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
            code=result.returncode
        except subprocess.TimeoutExpired:code=124
    entry=dict(module=name,exit_code=code)
    if xml.exists():
        suite=ET.parse(xml).getroot()[0]
        entry.update({key:int(suite.attrib.get(key,0)) for key in ('tests','failures','errors','skipped')})
    results.append(entry)
    (output/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(entry),flush=True)
sys.exit(1 if any(r['exit_code'] for r in results) else 0)
