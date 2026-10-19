"""Local reorganization alarms. These do not provide consensus finality."""
import json
from pathlib import Path
import threading
import time
from core_runtime import MAIN_GENESIS
from core_miner import exclusive_miner

class ChainGuard:
    def __init__(self,path,genesis=MAIN_GENESIS):
        self.path=Path(path);self.lock=threading.RLock();self.genesis=genesis
        self.state=json.loads(self.path.read_text()) if self.path.exists() else {'genesis':genesis,'anchors':{},'halted':False}
        if self.state.get('genesis')!=genesis:raise ValueError('Chain monitor belongs to another network')

    def observe(self,rpc):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.lock,exclusive_miner(self.path):
            if self.path.exists():self.state=json.loads(self.path.read_text())
            if self.state.get('genesis')!=self.genesis or rpc('getblockhash',0)!=self.genesis:raise ValueError('Unexpected network; payments blocked')
            height=rpc('getblockcount');tip=rpc('getblockhash',height)
            old=self.state.get('anchors',{})
            if old:
                previous=max(map(int,old));probe=min(height,previous)
                if str(probe) not in old or rpc('getblockhash',probe)!=old[str(probe)] or height<previous:
                    self.state.update(halted=True,reason='Previously observed blockchain history changed. Payments are paused pending review.',detected_at=time.time())
            anchors={str(h):(old[str(h)] if str(h) in old and not self.state['halted'] else rpc('getblockhash',h)) for h in range(max(0,height-143),height+1)}
            if rpc('getblockhash',height)!=tip:raise RuntimeError('Chain changed while checking payment safety')
            self.state.update(anchors=anchors,height=height,tip=tip,checked_at=time.time())
            self.path.parent.mkdir(parents=True,exist_ok=True)
            # A failure to persist monitoring must block payments rather than
            # silently erase the baseline. Existing files are never deleted.
            temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(self.state,indent=2))
            for attempt in range(30):
                try:temporary.replace(self.path);break
                except PermissionError:
                    if attempt==29:raise
                    time.sleep(.02)
            return dict(self.state)

    def require_payments(self,rpc):
        state=self.observe(rpc)
        if state['halted']:raise RuntimeError(state['reason'])

    def acknowledge(self,rpc):
        with self.lock:
            self.observe(rpc)
            self.state.update(halted=False,acknowledged_at=time.time())
            self.path.write_text(json.dumps(self.state,indent=2))
