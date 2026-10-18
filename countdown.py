"""Read-only launch clock and deadline QA worker. Never publishes a coin or opens ports."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
TARGET=datetime(2026,10,18,15,0,0,tzinfo=timezone.utc).timestamp()
STATE=ROOT/'runtime/countdown.json'

def save(value):
    temp=STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(value)); temp.replace(STATE)

def status(height):
    try: state=json.loads(STATE.read_text())
    except (OSError,ValueError): state={}
    return {'target_utc':'2026-10-18T15:00:00Z','server_time':time.time(),'height':height,
            'public_deployed':False,'launch_armed':False,
            'watcher_alive':time.time()-state.get('heartbeat',0)<45,
            'check_finished':state.get('check_finished',False),'check_summary':state.get('check_summary','')}

def main():
    ROOT.joinpath('runtime').mkdir(exist_ok=True)
    state={'heartbeat':time.time(),'check_finished':False,'launch_armed':False}
    while True:
        state['heartbeat']=time.time(); save(state)
        if time.time()>=TARGET and not state['check_finished']:
            state['check_summary']='Running the local consensus/wallet/network suite. No public launch is armed.'; save(state)
            try:
                result=subprocess.run([sys.executable,'-m','unittest','-v','test_pawquanta'],cwd=ROOT,
                                      capture_output=True,text=True,timeout=90)
                (ROOT/'reports/deadline-checks.txt').write_text(result.stdout+result.stderr)
                state['check_summary']=('Local tests passed. ' if result.returncode==0 else 'Local tests failed. ')+'Public deployment remains blocked pending isolation, protocol review and verified external mining.'
            except Exception as exc:
                state['check_summary']='Readiness check failed: '+type(exc).__name__+'. Public deployment remains blocked.'
            state['check_finished']=True
            state['heartbeat']=time.time(); save(state)
        time.sleep(10)

if __name__=='__main__': main()
