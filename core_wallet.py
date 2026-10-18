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

BASE=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent

class WalletApp:
    def __init__(self,window,manifest):
        self.window,self.manifest=window,manifest
        self.events=queue.Queue();self.runtime=self.tor=None;self.address=None;self.worker=None
        self.connection_worker=None
        self.closing=False
        self.profile=BASE/'Pawquanta-wallet-data';self.stop_file=self.profile/'STOP-MINING'
        window.title('Pawquanta — Wallet & Miner');window.geometry('700x470');window.minsize(620,430)
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
        actions=ttk.Frame(frame);actions.pack(fill='x')
        ttk.Button(actions,text='Receive / copy address',command=self.receive).pack(side='left',padx=(0,7))
        ttk.Button(actions,text='Send coins',command=self.send).pack(side='left',padx=7)
        ttk.Button(actions,text='Show backup folder',command=self.backup_folder).pack(side='left',padx=7)
        ttk.Label(frame,text='Mining is voluntary and uses one CPU worker. Newly mined coins mature after 100 blocks.\nCoins have no established value. Mining does not guarantee income.',wraplength=630).pack(anchor='w',pady=(16,0))
        window.protocol('WM_DELETE_WINDOW',self.close);window.after(200,self.poll)

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
                self.events.put(('connected',None))
                while not self.closing and self.runtime and self.runtime.process.poll() is None:
                    self.events.put(('snapshot',self.runtime.snapshot()));time.sleep(3)
            except Exception as error:
                if not self.closing:
                    if self.runtime:self.runtime.stop()
                    if self.tor:self.tor.stop()
                    self.events.put(('connect_error',str(error)))
        self.connection_worker=threading.Thread(target=work,daemon=True)
        self.connection_worker.start()

    def start_mining(self):
        if not self.runtime or not self.address:return
        if self.worker and self.worker.is_alive():return
        budget=simpledialog.askstring('Personal mining limit','Stop after how many mined PQUA?\nThis is your personal limit, not a network restriction.',initialvalue='1260000',parent=self.window)
        if budget is None:return
        try:
            amount=Decimal(budget);units=amount*UNIT
            if not amount.is_finite() or units!=units.to_integral_value() or not 0<units<=42_000_000*UNIT:raise ValueError()
        except (DecimalException,ValueError):messagebox.showerror('Mining limit','Enter a positive amount, with at most eight decimal places.');return
        if self.stop_file.exists():self.stop_file.unlink()
        config={'armed':True,'network':'pawquanta-main-v1','genesis':MAIN_GENESIS,
            'rpc_url':self.runtime.wallet.url,'cookie_file':str(self.runtime.wallet.cookie),
            'receiving_address':self.address,'ledger_file':str(self.profile/'mining-rewards.sqlite'),
            'limit_atomic_units':int(units),'not_before_utc_epoch':LAUNCH_EPOCH}
        def work():
            try:
                self.progress('Mining scheduled for launch' if time.time()<LAUNCH_EPOCH else 'Mining with one CPU worker…')
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
        recipient=simpledialog.askstring('Send PQUA','Receiving Pawquanta address:',parent=self.window)
        if not recipient:return
        raw=simpledialog.askstring('Send PQUA','Amount in PQUA:',parent=self.window)
        if raw is None:return
        try:
            amount=Decimal(raw)
            if not amount.is_finite() or not 0<amount<=42_000_000 or amount*UNIT!=(amount*UNIT).to_integral_value():raise ValueError()
        except (ValueError,DecimalException):messagebox.showerror('Amount','Enter a positive amount with at most eight decimal places.');return
        if not messagebox.askyesno('Confirm transfer',f'Send {amount} PQUA to\n{recipient}\nplus the network fee?'):return
        def work():
            try:
                password=(self.profile/'wallet-recovery-password.txt').read_text().strip()
                self.runtime.wallet('walletpassphrase',password,30)
                try:transaction=self.runtime.wallet('sendtoaddress',recipient,format(amount,'f'))
                finally:self.runtime.wallet('walletlock')
                self.progress('Transfer submitted: '+transaction)
            except Exception as error:self.events.put(('error',str(error)))
        threading.Thread(target=work,daemon=True).start()

    def backup_folder(self):
        if not self.profile.exists():return
        import os
        os.startfile(str(self.profile))
        messagebox.showinfo('Wallet backup','Keep the encrypted backup and recovery-password file somewhere safe.\nNever upload or share either file. Your wallet data is private to this computer.')

    def poll(self):
        while not self.events.empty():
            kind,value=self.events.get()
            if kind=='status':self.status.set(value)
            elif kind=='connected':self.mine_button.configure(state='normal');self.status.set('Encrypted wallet connected. You can receive, send or mine.')
            elif kind=='snapshot':
                self.balance.set('Spendable: '+value['spendable']+' PQUA');self.maturing.set('Maturing: '+value['maturing']+' PQUA')
                self.network.set(f"Block {value['height']:,} · {value['peers']} peer connections"+(' · Syncing…' if value['synchronizing'] else ''))
                self.mine_button.configure(state='normal' if value['peers']>0 and not value['synchronizing'] else 'disabled')
            elif kind=='error':self.status.set(value);messagebox.showerror('Pawquanta',value)
            elif kind=='connect_error':self.connect_button.configure(state='normal');self.status.set(value);messagebox.showerror('Connection',value)
            elif kind=='closed':self.window.destroy();return
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
        receiver=runtime.wallet('getnewaddress','self-test-receiver')
        password=(runtime.directory/'wallet-recovery-password.txt').read_text().strip()
        runtime.wallet('walletpassphrase',password,30)
        try:transaction=runtime.wallet('sendtoaddress',receiver,'10.00000001')
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
            'public_mainnet_verified':False,'mining_armed':False}
        (Path(directory)/'self-test-result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    finally:runtime.stop()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ui-smoke',action='store_true')
    parser.add_argument('--self-test',action='store_true');parser.add_argument('--self-test-data',type=Path);arguments=parser.parse_args()
    manifest_file=BASE/'core-release.json'
    manifest=json.loads(manifest_file.read_text()) if manifest_file.exists() else {'ready':False}
    if arguments.self_test:
        if not arguments.self_test_data:parser.error('--self-test-data is required')
        self_test(arguments.self_test_data,manifest);raise SystemExit()
    window=tk.Tk();app=WalletApp(window,manifest)
    if arguments.ui_smoke:window.withdraw();window.after(500,window.destroy)
    window.mainloop()
