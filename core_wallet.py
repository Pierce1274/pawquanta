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
from pdcrm import settings as compute_settings,save_settings as save_compute_settings,status_text as compute_status_text

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
        window.title('Pawquanta '+VERSION+' â€” Wallet & Miner');window.geometry('820x740');window.minsize(780,700)
        style=ttk.Style();style.theme_use('clam')
        style.configure('TFrame',background='#111820');style.configure('TLabel',background='#111820',foreground='#edf1f4',font=('Segoe UI',11))
        style.configure('Title.TLabel',font=('Segoe UI',26,'bold'));style.configure('Balance.TLabel',font=('Segoe UI',20,'bold'))
        style.configure('TButton',font=('Segoe UI',11),padding=9)
        frame=ttk.Frame(window,padding=24);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='PAWQUANTA',style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame,text='Your wallet. Your miner. A separate, experimental public blockchain.').pack(anchor='w',pady=(4,20))
        self.balance=tk.StringVar(value='Spendable: â€” PQUA');self.maturing=tk.StringVar(value='Maturing: â€” PQUA')
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
        ttk.Button(frame,text='PDCRM â€” CPU + GPU resources',command=self.resource_settings).pack(anchor='w',pady=4)
        self.compute_status=tk.StringVar(value='PDCRM: CPU requires verified temperature telemetry; GPU uses its watchdog.')
        ttk.Label(frame,textvariable=self.compute_status,wraplength=720).pack(anchor='w',pady=3)
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
        ttk.Label(frame,text='PDCRM supports simultaneous CPU + GPU hashing with one mining quota.\nUnavailable temperature sensors pause the affected worker. New coins mature after 100 blocks.\nCoins have no established value or guaranteed income.',wraplength=720).pack(anchor='w',pady=(12,0))
        window.protocol('WM_DELETE_WINDOW',self.close);window.after(200,self.poll)
        if self.updates:threading.Thread(target=self.update_loop,daemon=True).start()

    def resource_settings(self):
        if not self.runtime or not self.address:
            messagebox.showinfo('PDCRM','Connect your wallet before changing resource settings.');return
        import os
        panel=tk.Toplevel(self.window);panel.title('PDCRM â€” compute resources');panel.geometry('650x560')
        frame=ttk.Frame(panel,padding=20);frame.pack(fill='both',expand=True)
        value=compute_settings(self.profile)
        cpu=tk.IntVar(value=value['cpu_workers']);cpu_duty=tk.IntVar(value=round(value['cpu_duty']*100));gpu_duty=tk.IntVar(value=round(value['gpu_duty']*100))
        ttk.Label(frame,text='Pawquanta Dynamic Compute Resource Manager',font=('Segoe UI',14,'bold')).pack(anchor='w')
        for label,variable,lower,upper in [('CPU workers (logical processors)',cpu,0,min(64,os.cpu_count() or 1)),('CPU work duty (%)',cpu_duty,5,100),('GPU work duty (%)',gpu_duty,5,100)]:
            row=ttk.Frame(frame);row.pack(fill='x',pady=8);ttk.Label(row,text=label).pack(side='left');ttk.Spinbox(row,from_=lower,to=upper,textvariable=variable,width=8).pack(side='right')
        ttk.Label(frame,text='CPU and GPU can run together. Duty is a work budget, not a guarantee of\nTask Manager utilization. CPU: pause 80Â°C / resume 70Â°C / stop 85Â°C.\nGPU: pause 68Â°C / resume 66Â°C / stop 75Â°C, plus power limits.\nApple uses system thermal pressure instead of invented temperatures.\nWindows CPU mining needs a running CPU-temperature monitor.\nNo sensor means no CPU hashing. The app never installs a kernel driver.\nThese are conservative policy limits, not your manufacturerâ€™s ratings.',wraplength=600).pack(anchor='w',pady=10)
        ttk.Button(frame,text='CPU temperature setup / check',command=self.cpu_setup).pack(anchor='w',pady=4)
        manual=tk.BooleanVar(value=value.get('manual_cpu',False))
        ttk.Checkbutton(frame,text='Manual CPU mode when temperature readings are unavailable',variable=manual).pack(anchor='w',pady=5)
        ttk.Label(frame,text='Manual mode cannot detect CPU overheating without sensors. Start with 1 worker at 25% duty. Stop mining if the computer becomes hot or unstable.',wraplength=590).pack(anchor='w',pady=5)
        def apply():
            try:
                if manual.get() and not value.get('manual_cpu',False):
                    if not messagebox.askyesno('Manual CPU mode','Without CPU temperature readings, automatic CPU overheating protection is unavailable. Enable manual mode on this computer?',parent=panel):return
                    cpu.set(min(cpu.get() or 1,1));cpu_duty.set(min(cpu_duty.get(),25))
                save_compute_settings(self.profile,{'cpu_workers':cpu.get(),'cpu_duty':cpu_duty.get()/100,'gpu_duty':gpu_duty.get()/100,'manual_cpu':manual.get()})
                self.compute_status.set('PDCRM settings saved. Manual mode has no CPU temperature protection when readings are missing.');panel.destroy()
            except (ValueError,tk.TclError,OSError) as error:messagebox.showerror('PDCRM',str(error),parent=panel)
        ttk.Button(frame,text='Apply live resource settings',command=apply).pack(anchor='w')

    def cpu_setup(self):
        import webbrowser
        panel=tk.Toplevel(self.window);panel.title('CPU temperature setup');panel.geometry('650x460')
        frame=ttk.Frame(panel,padding=20);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='CPU mining needs real temperature readings',font=('Segoe UI',15,'bold')).pack(anchor='w')
        text=('Windows:\n1. With the PC ownerâ€™s permission, obtain Libre Hardware Monitor from its official GitHub release. Some sensors require administrator permission.\n2. Keep the monitor running and confirm it shows CPU Package/Core temperatures.\n3. For newer releases, configure Remote Web Server to listen on 127.0.0.1, port 8085, then enable Run. Do not open a router port or expose the monitor to the internet. Older WMI providers remain supported.\n4. Click Check readings below. CPU hashing resumes automatically when valid readings become available and CPU workers are selected.\n\nOn Mac, the supported system thermal-pressure reading is used.\nIntel integrated Arc GPU mining is not supported. No sensors or drivers are installed by this wallet.')
        ttk.Label(frame,text=text,wraplength=605).pack(anchor='w',pady=12)
        result=tk.StringVar(value='Checking has not started.')
        ttk.Label(frame,textvariable=result,wraplength=600).pack(anchor='w',pady=5)
        def check():
            result.set('Checking local temperature readingsâ€¦')
            def work():
                try:
                    from pdcrm import cpu_telemetry
                    reading=cpu_telemetry()
                    message=(f"CPU temperature: {reading['temperature_c']:.1f}Â°C Â· "+reading.get('source','verified sensor')) if 'temperature_c' in reading else 'System thermal-pressure reading available.'
                except Exception:message='No verified readings. Keep the monitor running and check the local-only server settings. CPU hashing stays paused.'
                self.events.put(('sensor_check',(panel,result,message)))
            threading.Thread(target=work,daemon=True).start()
        row=ttk.Frame(frame);row.pack(fill='x')
        ttk.Button(row,text='Check readings',command=check).pack(side='left')
        ttk.Button(row,text='Official monitor downloads',command=lambda:webbrowser.open('https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases')).pack(side='left',padx=10)

    def update_loop(self):
        while not self.closing:
            if self.updates.enabled():
                try:
                    release=self.updates.check()
                    if release:self.events.put(('update_ready',release));return
                except Exception as error:self.events.put(('update_status','Update check unavailable; wallet continues working. '+str(error)))
            for _ in range(15*60):
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
                    try:self.events.put(('chain',self.guard.observe(self.runtime.rpc)))
                    except (OSError,ValueError,RuntimeError) as error:self.events.put(('chain_error',str(error)))
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
        try:
            if not self.gpu.get() and compute_settings(self.profile)['cpu_workers']==0:
                self.progress('Select GPU mining or choose CPU workers in PDCRM before starting.');return
        except (OSError,ValueError) as error:
            self.progress('PDCRM settings need attention: '+str(error));return
        if resume:
            try:budget=str(Decimal(json.loads((self.profile/'mining-preferences.json').read_text())['limit_atomic_units'])/UNIT)
            except (OSError,ValueError,KeyError):self.progress('Mining was not resumed because saved preferences are unavailable.');return
        else:budget=simpledialog.askstring('Personal mining limit','Stop after how many mined PQUA?\nThis is your personal limit, not a network restriction.',initialvalue='1260000',parent=self.window)
        if budget is None:return
        try:
            amount=Decimal(budget);units=amount*UNIT
            if not amount.is_finite() or units!=units.to_integral_value() or not 0<units<=42_000_000*UNIT:raise ValueError()
        except (DecimalException,ValueError):messagebox.showerror('Mining limit','Enter a positive amount, with at most eight decimal places.');return
        if not resume:
            from mining_schedule import cancel
            cancel(self.profile)
        if self.stop_file.exists():self.stop_file.unlink()
        (self.profile/'mining-preferences.json').write_text(json.dumps({'limit_atomic_units':int(units),'gpu':self.gpu.get()}))
        config={'armed':True,'network':'pawquanta-main-v1','genesis':MAIN_GENESIS,
            'rpc_url':self.runtime.wallet.url,'cookie_file':str(self.runtime.wallet.cookie),
            'receiving_address':self.address,'ledger_file':str(self.profile/'mining-rewards.sqlite'),
            'limit_atomic_units':int(units),'not_before_utc_epoch':LAUNCH_EPOCH,'gpu':self.gpu.get(),'pdcrm':True}
        def work():
            try:
                self.progress('Preparing PDCRM workers. Check the live hashing status below; missing sensors pause CPU work.')
                mine(config,self.stop_file,owner_limit_enforced=False)
                self.progress('Mining stopped. Your wallet stays connected.')
            except Exception as error:self.events.put(('error',str(error)))
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()

    def stop_mining(self,cancel_schedule=True):
        if cancel_schedule:
            from mining_schedule import cancel
            cancel(self.profile)
        if self.profile.exists():self.stop_file.touch()
        self.status.set('Stopping miningâ€¦')

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
        if not self.closing:
            try:
                from mining_schedule import read as read_schedule,update as update_schedule
                schedule=read_schedule(self.profile)
                if schedule and schedule['state']=='paused':
                    if time.time()<schedule['resume_at_utc']:
                        self.resume_when_synced=False
                        if self.worker and self.worker.is_alive():self.stop_file.touch()
                        self.status.set('Mining paused by schedule. Automatic resume is scheduled; Stop mining cancels it.')
                    else:
                        update_schedule(self.profile,schedule,'resume_requested');self.resume_when_synced=True
                        if not self.runtime and not (self.connection_worker and self.connection_worker.is_alive()):self.connect()
            except (OSError,ValueError,KeyError) as error:
                self.resume_when_synced=False
                if self.profile.exists():self.stop_file.touch()
                self.status.set('Mining schedule needs attention: '+str(error))
        try:
            compute=json.loads((self.profile/'pdcrm-status.json').read_text())
            if not self.worker or not self.worker.is_alive() or self.stop_file.exists():self.compute_status.set('Mining stopped. No hashing workers are active.')
            elif time.time()-compute['updated_at']<5:self.compute_status.set(compute_status_text(compute))
            else:self.compute_status.set('Waiting for fresh miner telemetry â€” hashing is not confirmed.')
        except (OSError,ValueError,KeyError,AttributeError):pass
        while not self.events.empty():
            kind,value=self.events.get()
            if kind=='status':self.status.set(value)
            elif kind=='sensor_check':
                panel,result,message=value
                if panel.winfo_exists():result.set(message)
            elif kind=='chain':self.chain_status.set('PAYMENTS PAUSED â€” '+value['reason'] if value.get('halted') else 'Chain monitor active. Low-hashrate PoW remains vulnerable to majority attacks.')
            elif kind=='chain_error':self.chain_status.set('PAYMENTS PAUSED â€” Chain monitor unavailable: '+value)
            elif kind=='update_status':self.status.set(value)
            elif kind=='update_ready':
                self.update_ready=value
                self.status.set('Approved update '+value['version']+' downloaded. Restarting in 30 seconds; uncheck automatic updates to defer.')
                self.window.after(30000,self.apply_update)
            elif kind=='connected':self.mine_button.configure(state='normal');self.status.set('Encrypted wallet connected. You can receive, send or mine.')
            elif kind=='snapshot':
                self.balance.set('Spendable: '+format(Decimal(value['spendable']),',.8f')+' PQUA');self.maturing.set('Maturing: '+format(Decimal(value['maturing']),',.8f')+' PQUA')
                self.network.set(f"Block {value['height']:,} of {value.get('headers',value['height']):,} Â· {value['peers']} peer connections"+(' Â· Syncingâ€¦' if value['synchronizing'] else ''))
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
        self.stop_mining(cancel_schedule=False);self.status.set('Safely closing your wallet and network connectionâ€¦')
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
        # Real spawned CPU workers, native block validation and a one-atomic-unit
        # quota. Sensor readings are fixtures here, never a hardware claim.
        from unittest.mock import patch
        from pdcrm import save_settings as save_pdcrm
        from core_miner import mine as mine_pdcrm
        compute_profile=runtime.directory/'pdcrm-private-check';compute_profile.mkdir()
        save_pdcrm(compute_profile,{'cpu_workers':2,'cpu_duty':1,'gpu_duty':.5})
        compute_address=runtime.wallet('getnewaddress','pdcrm-private-check')
        config={'armed':True,'genesis':runtime.genesis,'rpc_url':runtime.wallet.url,
            'cookie_file':str(runtime.wallet.cookie),'receiving_address':compute_address,
            'ledger_file':str(compute_profile/'quota.sqlite'),'limit_atomic_units':1,
            'not_before_utc_epoch':0,'pdcrm':True,'gpu':False}
        with patch('pdcrm.cpu_telemetry',return_value={'temperature_c':50}):
            mine_pdcrm(config,compute_profile/'STOP',development=True,owner_limit_enforced=False)
        import sqlite3
        with sqlite3.connect(compute_profile/'quota.sqlite') as database:
            assert database.execute('select sum(units) from rewards').fetchone()[0]==1
        assert json.loads((compute_profile/'pdcrm-status.json').read_text())['cpu_hashes']>0
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
            'pdcrm_spawned_cpu_native_block_and_exact_quota':True,
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
