"""Test an actual Connect/Close race without opening a native window."""
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import core_wallet

class Value:
    def set(self,value):self.value=value
    def configure(self,**values):pass

class WalletShutdownTests(unittest.TestCase):
    def test_close_waits_for_connect_before_stopping_its_node(self):
        started=threading.Event();allow_start=threading.Event();order=[]
        class Node:
            def __init__(self,*args,**kwargs):self.process=type('Process',(),{'poll':lambda self:None})()
            def start(self):
                started.set()
                if not allow_start.wait(3):raise TimeoutError('Test setup was not released')
                order.append('started')
            def open_wallet(self):return 'fixture-address'
            def stop(self):order.append('node-stopped');return True
        class Tor:
            port=19000
            def __init__(self,*args,**kwargs):pass
            def start(self):pass
            def stop(self):order.append('tor-stopped');return True
        with tempfile.TemporaryDirectory() as directory,patch.object(core_wallet,'CoreRuntime',Node),patch.object(core_wallet,'TorClient',Tor):
            app=core_wallet.WalletApp.__new__(core_wallet.WalletApp)
            app.profile=Path(directory);app.stop_file=app.profile/'STOP'
            app.events=queue.Queue();app.runtime=app.tor=None;app.worker=app.connection_worker=None
            app.closing=False;app.address=None;app.connect_button=Value();app.status=Value()
            app.manifest={'ready':True,'seed_nodes':['fixture.onion:18731'],
                'windows_node_file':'fixture.exe','windows_node_sha256':'a'*64}
            app.connect();self.assertTrue(started.wait(2));app.close()
            self.assertNotIn('node-stopped',order)
            allow_start.set()
            deadline=time.monotonic()+3;closed=False
            while time.monotonic()<deadline:
                try:event,_=app.events.get(timeout=.1)
                except queue.Empty:continue
                if event=='closed':closed=True;break
            self.assertTrue(closed);self.assertEqual(order,['started','node-stopped','tor-stopped'])
            self.assertFalse(app.connection_worker.is_alive())

if __name__=='__main__':unittest.main()
