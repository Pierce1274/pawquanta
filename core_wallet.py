"""Pawquanta desktop wallet and miner. SPDX-License-Identifier: MIT"""
import argparse
from decimal import Decimal,InvalidOperation,DecimalException
import json
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk,messagebox,simpledialog
from core_runtime import CoreRuntime,MAIN_GENESIS,LAUNCH_EPOCH,file_hash
from core_tor import TorClient
from core_miner import mine,UNIT,APPROVED_LIMIT
from chain_guard import ChainGuard
from wallet_updates import WalletUpdates,VERSION,launch as launch_updated

BASE=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
PROFILE=Path.home()/'Library/Application Support/Pawquanta' if sys.platform=='darwin' else BASE/'Pawquanta-wallet-data'
UPDATE_STORE=Path.home()/'Library/Application Support/Pawquanta-Updates' if sys.platform=='darwin' else BASE/'.wallet-updates'
UPDATES_TEST_MODE=False

class WalletApp:
    def __init__(self,window,manifest):
        self.window,self.manifest=window,manifest
        self.events=queue.Queue();self.runtime=self.tor=None;self.address=None;self.worker=None
        self.connection_worker=None
        self.closing=False
        self.profile=PROFILE;self.stop_file=self.profile/'STOP-MINING'
        self.guard=None;self.update_ready=None;self.sending=False;self.updates=None;self.resume_after_update=False
        window.title('Pawquanta '+VERSION+' — Wallet & Miner');window.geometry('780x650');window.minsize(740,600)
        style=ttk.Style();style.theme_use('clam')
        style.configure('TFrame',background='#111820');style.configure('TLabel',background='#111820',foreground='#edf1f4',font=('Segoe UI',11))
        style.configure('Title.TLabel',font=('Segoe UI',26,'bold'));style.configure('Balance.TLabel',font=('Segoe UI',20,'bold'))
        style.configure('TButton',font=('Segoe UI',11),padding=9)
        frame=ttk.Frame(window,padding=24);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='PAWQUANTA',style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame,text='Your wallet. Your miner. A separate, experimental public blockchain.').pack(anchor='w',pady=(4,20))
        self.balance=tk.StringVar(value='Spendable: — PQUA');self.maturing=tk.StringVar(value='Maturing: — PQUA')
        ttk.Label(frame,textvariable=self.balance,style='Balance.TLabel').pack(anchor='w')
        ttk.Label(frame,textvariable=self.maturing).pack(anchor='w',pady=5)
        self.network=tk.StringVar(value='Not connected');ttk.Label(frame,textvariable=self.network).pack(anchor='w',pady=8)
        self.status=tk.StringVar(value='Click Connect. The network connection downloads automatically if needed.')
        ttk.Label(frame,textvariable=self.status,wraplength=630).pack(anchor='w',pady=8)
        buttons=ttk.Frame(frame);buttons.pack(fill='x',pady=12)
        self.connect_button=ttk.Button(buttons,text='Connect',command=self.connect);self.connect_button.pack(side='left',padx=(0,7))
        self.mine_button=ttk.Button(buttons,text='Start mining',command=self.start_mining,state='disabled');self.mine_button.pack(side='left',padx=7)
        ttk.Button(buttons,text='Stop mining',command=self.stop_mining).pack(side='left',padx=7)
        self.gpu=tk.BooleanVar(value=False)
        ttk.Checkbutton(frame,text='Use NVIDIA / Apple Metal GPU (guarded, low load)',variable=self.gpu).pack(anchor='w')
        bootstrap=BASE/'update-root.json'
        if bootstrap.exists() and not UPDATES_TEST_MODE:self.updates=WalletUpdates(UPDATE_STORE,bootstrap.read_bytes(),self.progress)
        self.auto_update=tk.BooleanVar(value=self.updates.enabled() if self.updates else False)
        ttk.Checkbutton(frame,text='Automatically install publisher-approved updates (restarts this app)',variable=self.auto_update,
            command=lambda:self.updates.set_enabled(self.auto_update.get()) if self.updates else None).pack(anchor='w')
        self.chain_status=tk.StringVar(value='Experimental PoW network: confirmations do not guarantee finality.')
        ttk.Label(frame,textvariable=self.chain_status,wraplength=700).pack(anchor='w',pady=5)
        ttk.Button(frame,text='Review chain warning',command=self.review_chain).pack(anchor='w')
        actions=ttk.Frame(frame);actions.pack(fill='x')
        ttk.Button(actions,text='Receive / copy address',command=self.receive).pack(side='left',padx=(0,7))
        ttk.Button(actions,text='Send coins',command=self.send).pack(side='left',padx=7)
        ttk.Button(actions,text='Show backup folder',command=self.backup_folder).pack(side='left',padx=7)
        ttk.Label(frame,text='Choose CPU or guarded NVIDIA / Apple Metal GPU mining. GPU pauses when hot.\nNew coins mature after 100 blocks. Coins have no established value or guaranteed income.',wraplength=670).pack(anchor='w',pady=(16,0))
        window.protocol('WM_DELETE_WINDOW',self.close);window.after(200,self.poll)
        if self.updates:threading.Thread(target=self.update_loop,daemon=True).start()

    def update_loop(self):
        while not self.closing:
            if self.updates.enabled():
                try:
                    release=self.updates.check()
                    if release:self.events.put(('update_ready',release));return
                except Exception as error:self.events.put(('update_status','Update check unavailable; wallet continues working. '+str(error)))
            for _ in range(6*60*60):
                if self.closing:return
                time.sleep(1)

    def apply_update(self):
        if not self.updates or not self.auto_update.get() or self.closing:return
        if self.sending:self.window.after(5000,self.apply_update);return
        self.resume_after_update=bool(self.worker and self.worker.is_alive() and not self.stop_file.exists())
        self.close()

    def review_chain(self):
        if not self.guard or not self.runtime:return
        state=self.guard.observe(self.runtime.rpc)
        if not state.get('halted'):
            messagebox.showinfo('Chain monitoring','No history change detected since this wallet began monitoring. This is not a guarantee of finality.');return
        if messagebox.askyesno('Review blockchain history',state.get('reason','Chain warning')+'\n\nOnly acknowledge after independently checking the chain. Accept the currently observed history and enable payments?'):
            self.guard.acknowledge(self.runtime.rpc)

    def progress(self,message):self.events.put(('status',message))

    def connect(self):
        self.connect_button.configure(state='disabled')
        def work():
            try:
                if self.manifest.get('ready') is not True:raise ValueError('This development package is not armed for the public network')
                seed=self.manifest['seed_nodes'][0]
                self.tor=TorClient(self.profile/'transport',self.progress)
                self.runtime=CoreRuntime(self.profile,BASE/self.manifest['windows_node_file'],
                    self.manifest['windows_node_sha256'],seed=seed,socks_port=self.tor.port,status=self.progress)
                self.tor.start();self.runtime.start();self.address=self.runtime.open_wallet()
                self.guard=ChainGuard(self.profile/'chain-monitor.json')
                self.events.put(('connected',None))
                while not self.closing and self.runtime and self.runtime.process.poll() is None:
                    self.events.put(('chain',self.guard.observe(self.runtime.rpc)))
                    self.events.put(('snapshot',self.runtime.snapshot()));time.sleep(3)
            except Exception as error:
                if not self.closing:
                    if self.runtime:self.runtime.stop()
                    if self.tor:self.tor.stop()
                    self.events.put(('connect_error',str(error)))
        self.connection_worker=threading.Thread(target=work,daemon=True)
        self.connection_worker.start()

    def start_mining(self,resume=False):
        if not self.runtime or not self.address:return
        if self.worker and self.worker.is_alive():return
        if resume:
            try:budget=str(Decimal(json.loads((self.profile/'mining-preferences.json').read_text())['limit_atomic_units'])/UNIT)
            except (OSError,ValueError,KeyError):self.progress('Mining was not resumed because saved preferences are unavailable.');return
        else:budget=simpledialog.askstring('Personal mining limit','Stop after how many mined PQUA?\nThis is your personal limit, not a network restriction.',initialvalue='1260000',parent=self.window)
        if budget is None:return
        try:
            amount=Decimal(budget);units=amount*UNIT
            if not amount.is_finite() or units!=units.to_integral_value() or not 0<units<=42_000_000*UNIT:raise ValueError()
        except (DecimalException,ValueError):messagebox.showerror('Mining limit','Enter a positive amount, with at most eight decimal places.');return
        if self.stop_file.exists():self.stop_file.unlink()
        (self.profile/'mining-preferences.json').write_text(json.dumps({'limit_atomic_units':int(units),'gpu':self.gpu.get()}))
        config={'armed':True,'network':'pawquanta-main-v1','genesis':MAIN_GENESIS,
            'rpc_url':self.runtime.wallet.url,'cookie_file':str(self.runtime.wallet.cookie),
            'receiving_address':self.address,'ledger_file':str(self.profile/'mining-rewards.sqlite'),
            'limit_atomic_units':int(units),'not_before_utc_epoch':LAUNCH_EPOCH,'gpu':self.gpu.get()}
        def work():
            try:
                self.progress('Mining scheduled for launch' if time.time()<LAUNCH_EPOCH else ('Mining with guarded NVIDIA GPU…' if config['gpu'] else 'Mining with one CPU worker…'))
                mine(config,self.stop_file,owner_limit_enforced=False)
                self.progress('Mining stopped. Your wallet stays connected.')
            except Exception as error:self.events.put(('error',str(error)))
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()

    def stop_mining(self):
        if self.profile.exists():self.stop_file.touch()
        self.status.set('Stopping mining…')

    def receive(self):
        if not self.address:messagebox.showinfo('Receive','Connect first to create or load your encrypted wallet.');return
        self.window.clipboard_clear();self.window.clipboard_append(self.address)
        messagebox.showinfo('Address copied',self.address+'\n\nOnly send Pawquanta on this network to this address.')

    def send(self):
        if not self.runtime or not self.address:return
        if self.sending:return
        self.sending=True
        recipient=simpledialog.askstring('Send PQUA','Receiving Pawquanta address:',parent=self.window)
        if not recipient:self.sending=False;return
        raw=simpledialog.askstring('Send PQUA','Amount in PQUA:',parent=self.window)
        if raw is None:self.sending=False;return
        try:
            amount=Decimal(raw)
            if not amount.is_finite() or not 0<amount<=42_000_000 or amount*UNIT!=(amount*UNIT).to_integral_value():raise ValueError()
        except (ValueError,DecimalException):self.sending=False;messagebox.showerror('Amount','Enter a positive amount with at most eight decimal places.');return
        if not messagebox.askyesno('Confirm transfer',f'Send {amount} PQUA to\n{recipient}\nplus the network fee?'):self.sending=False;return
        def work():
            try:
                self.sending=True
                if not self.guard:raise RuntimeError('Chain monitor not ready; payments paused')
                self.guard.require_payments(self.runtime.rpc)
                password=(self.profile/'wallet-recovery-password.txt').read_text().strip()
                self.runtime.wallet('walletpassphrase',password,30)
                try:
                    result=self.runtime.wallet('send',{recipient:format(amount,'f')},None,'unset',None,{'minconf':12,'include_unsafe':False})
                    transaction=result['txid']
                finally:self.runtime.wallet('walletlock')
                self.progress('Transfer submitted: '+transaction)
            except Exception as error:self.events.put(('error',str(error)))
            finally:self.sending=False
        threading.Thread(target=work,daemon=True).start()

    def backup_folder(self):
        if not self.profile.exists():return
        import os
        if sys.platform=='darwin':
            import subprocess
            subprocess.Popen(['open',str(self.profile)])
        else:os.startfile(str(self.profile))
        messagebox.showinfo('Wallet backup','Keep the encrypted backup and recovery-password file somewhere safe.\nNever upload or share either file. Your wallet data is private to this computer.')

    def poll(self):
        while not self.events.empty():
            kind,value=self.events.get()
            if kind=='status':self.status.set(value)
            elif kind=='chain':self.chain_status.set('PAYMENTS PAUSED — '+value['reason'] if value.get('halted') else 'Chain monitor active. Low-hashrate PoW remains vulnerable to majority attacks.')
            elif kind=='update_status':self.status.set(value)
            elif kind=='update_ready':
                self.update_ready=value
                self.status.set('Approved update '+value['version']+' downloaded. Restarting in 30 seconds; uncheck automatic updates to defer.')
                self.window.after(30000,self.apply_update)
            elif kind=='connected':self.mine_button.configure(state='normal');self.status.set('Encrypted wallet connected. You can receive, send or mine.')
            elif kind=='snapshot':
                self.balance.set('Spendable: '+value['spendable']+' PQUA');self.maturing.set('Maturing: '+value['maturing']+' PQUA')
                self.network.set(f"Block {value['height']:,} · {value['peers']} peer connections"+(' · Syncing…' if value['synchronizing'] else ''))
                self.mine_button.configure(state='normal' if value['peers']>0 and not value['synchronizing'] else 'disabled')
                if getattr(self,'resume_when_synced',False) and value['peers']>0 and not value['synchronizing']:
                    self.resume_when_synced=False
                    try:self.gpu.set(json.loads((self.profile/'mining-preferences.json').read_text()).get('gpu',False))
                    except (OSError,ValueError):pass
                    self.start_mining(resume=True)
            elif kind=='error':self.status.set(value);messagebox.showerror('Pawquanta',value)
            elif kind=='connect_error':self.connect_button.configure(state='normal');self.status.set(value);messagebox.showerror('Connection',value)
            elif kind=='closed':
                if self.update_ready and self.updates and self.auto_update.get():
                    try:
                        executable=self.updates.install()
                        if executable:launch_updated(executable,self.profile,UPDATE_STORE,resume_connection=True,resume_mining=self.resume_after_update)
                    except Exception as error:
                        self.update_ready=None;self.closing=False;self.resume_when_synced=self.resume_after_update
                        self.status.set('Update deferred; restarting the existing wallet. '+str(error))
                        self.connect_button.configure(state='normal')
                        self.window.after(100,self.connect);self.window.after(200,self.poll);return
                self.window.destroy();return
        self.window.after(200,self.poll)

    def close(self):
        self.closing=True
        self.stop_mining();self.status.set('Safely closing your wallet and network connection…')
        def work():
            if self.connection_worker:
                self.connection_worker.join(timeout=365)
                if self.connection_worker.is_alive():
                    self.events.put(('error','Connection setup is still closing. Please wait before closing again.'));return
            if self.worker:self.worker.join(timeout=35)
            if self.runtime and not self.runtime.stop():self.events.put(('error','Node is still shutting down. Please wait before closing again.'));return
            if self.tor and not self.tor.stop():self.events.put(('error','Network connection is still shutting down. Please wait.'));return
            self.events.put(('closed',None))
        threading.Thread(target=work,daemon=True).start()

def self_test(directory,manifest):
    """Exercise encrypted wallet persistence and signed transfer on a private chain."""
    from core_miner import candidate,sha256d,target_from_bits
    import struct
    runtime=CoreRuntime(directory,BASE/manifest['windows_node_file'],manifest['windows_node_sha256'],
        genesis='0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206',development=True)
    try:
        runtime.start();address=runtime.open_wallet()
        template=runtime.wallet('getblocktemplate',{'rules':['segwit']})
        script=runtime.wallet('getaddressinfo',address)['scriptPubKey']
        header,body=candidate(template,script,1);target=target_from_bits(template['bits'])
        for nonce in range(10000):
            block_header=header+struct.pack('<I',nonce)
            if int.from_bytes(sha256d(block_header),'little')<=target:
                assert runtime.rpc('submitblock',(block_header+body).hex()) is None;break
        else:raise AssertionError('Private test work was not found')
        for _ in range(21):runtime.wallet('generatetoaddress',5,address)
        guard=ChainGuard(runtime.directory/'private-test-monitor.json',genesis=runtime.genesis)
        guard.observe(runtime.rpc);original=runtime.rpc('getbestblockhash')
        runtime.rpc('invalidateblock',original)
        try:guard.require_payments(runtime.rpc)
        except RuntimeError:pass
        else:raise AssertionError('A real private-chain reorganization did not block payments')
        assert ChainGuard(guard.path,genesis=runtime.genesis).state['halted']
        runtime.rpc('reconsiderblock',original);guard.acknowledge(runtime.rpc)
        receiver=runtime.wallet('getnewaddress','self-test-receiver')
        password=(runtime.directory/'wallet-recovery-password.txt').read_text().strip()
        runtime.wallet('walletpassphrase',password,30)
        try:
            guard.require_payments(runtime.rpc)
            transaction=runtime.wallet('send',{receiver:'10.00000001'},None,'unset',None,{'minconf':12,'include_unsafe':False})['txid']
        finally:runtime.wallet('walletlock')
        runtime.wallet('generatetoaddress',1,address)
        assert runtime.wallet('gettransaction',transaction)['confirmations']>=1
        assert runtime.stop()
        runtime.start();assert runtime.open_wallet()==address
        assert runtime.wallet('getwalletinfo')['unlocked_until']==0
        result={'passed':True,'scope':'desktop_wallet_private_payment_and_restart',
            'packaged_executable':bool(getattr(sys,'frozen',False)),
            'encrypted_wallet':True,'wallet_locked':True,'backup_exists':(runtime.directory/'wallet-encrypted-backup.dat').is_file(),
            'one_atomic_unit_coinbase':True,'decimal_transfer_confirmed':True,'restart_persistence':True,
            'real_reorg_alarm_persisted':True,'minimum_12_confirmation_send':True,
            'public_mainnet_verified':False,'mining_armed':False}
        (Path(directory)/'self-test-result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    finally:runtime.stop()


if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ui-smoke',action='store_true')
    parser.add_argument('--gpu-self-test',type=Path)
    parser.add_argument('--wallet-directory',type=Path)
    parser.add_argument('--update-directory',type=Path)
    parser.add_argument('--resume-connection',action='store_true')
    parser.add_argument('--resume-mining',action='store_true')
    parser.add_argument('--self-test',action='store_true');parser.add_argument('--self-test-data',type=Path);arguments=parser.parse_args()
    manifest_file=BASE/'core-release.json'
    manifest=json.loads(manifest_file.read_text()) if manifest_file.exists() else {'ready':False}
    UPDATES_TEST_MODE=arguments.ui_smoke
    if arguments.wallet_directory:PROFILE=arguments.wallet_directory.resolve()
    if arguments.update_directory:UPDATE_STORE=arguments.update_directory.resolve()
    if not arguments.ui_smoke and not arguments.self_test and not arguments.gpu_self_test and (BASE/'update-root.json').exists():
        bootstrap_client=WalletUpdates(UPDATE_STORE,(BASE/'update-root.json').read_bytes())
        newer=bootstrap_client.installed()
        if newer:launch_updated(newer,PROFILE,UPDATE_STORE,resume_connection=arguments.resume_connection,resume_mining=arguments.resume_mining);raise SystemExit()
    if arguments.gpu_self_test:
        from gpu_miner import GPUWorker
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            gpu=GPUWorker(Path(directory)/'STOP')
            try:
                nonce=gpu.search(bytes(range(76)),2**256-1)
                arguments.gpu_self_test.write_text(json.dumps({'passed':nonce is not None,'device':gpu.device,'sample':gpu.last_sample}))
            finally:gpu.close()
        raise SystemExit()
    if arguments.self_test:
        if not arguments.self_test_data:parser.error('--self-test-data is required')
        self_test(arguments.self_test_data,manifest);raise SystemExit()
    window=tk.Tk();app=WalletApp(window,manifest)
    app.resume_when_synced=arguments.resume_mining
    if arguments.resume_connection:window.after(100,app.connect)
    if arguments.ui_smoke:window.withdraw();window.after(500,window.destroy)
    window.mainloop()
