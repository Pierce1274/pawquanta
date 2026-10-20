"""Native desktop tools for Pawquanta 1.0. SPDX-License-Identifier: MIT"""
import datetime as dt,json,os,threading,time
from decimal import Decimal
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox,simpledialog,filedialog
import wallet_v1 as features


def task(app,fn,callback):
    def work():
        try:result=fn();error=None
        except Exception as exc:result=None;error=str(exc) or type(exc).__name__
        app.events.put(('ui_task',(callback,result,error)))
    threading.Thread(target=work,daemon=True).start()


def connected(app):
    if not app.runtime or not app.address:raise ValueError('Connect your wallet first.')
    return app.runtime


def panel(app,title,size='900x620'):
    window=tk.Toplevel(app.window);window.title(title);window.geometry(size)
    frame=ttk.Frame(window,padding=20);frame.pack(fill='both',expand=True)
    return window,frame


def error(app,text):messagebox.showerror('Pawquanta',text,parent=app.window)


def receive(app):
    if not app.address:messagebox.showinfo('Receive','Connect your wallet first.',parent=app.window);return
    window,frame=panel(app,'Receive Pawquanta','520x600')
    ttk.Label(frame,text='Receive PQUA',style='Title.TLabel').pack(anchor='w')
    ttk.Label(frame,text='Pawquanta network only. Verify the complete address.',wraplength=470).pack(anchor='w',pady=8)
    canvas=tk.Canvas(frame,width=320,height=320,bg='white',highlightthickness=0);canvas.pack(pady=10)
    import qrcode
    qr=qrcode.QRCode(border=4,error_correction=qrcode.constants.ERROR_CORRECT_M);qr.add_data(app.address);qr.make(fit=True);matrix=qr.get_matrix();scale=max(1,320//len(matrix));offset=(320-len(matrix)*scale)//2
    for y,row in enumerate(matrix):
        for x,black in enumerate(row):
            if black:canvas.create_rectangle(offset+x*scale,offset+y*scale,offset+(x+1)*scale,offset+(y+1)*scale,fill='black',outline='')
    text=tk.Entry(frame);text.insert(0,app.address);text.configure(state='readonly');text.pack(fill='x',pady=8)
    def copy():window.clipboard_clear();window.clipboard_append(app.address)
    ttk.Button(frame,text='Copy receiving address',command=copy).pack(anchor='w')


def send(app):
    if not app.runtime or not app.address:error(app,'Connect your wallet first.');return
    if app.sending:error(app,'A wallet transaction is already being prepared.');return
    window,frame=panel(app,'Send PQUA — review recipient and fee','690x450')
    recipient=tk.StringVar();amount=tk.StringVar();label=tk.StringVar();status=tk.StringVar(value='No transaction will be sent without your final confirmation.')
    book=features.address_book(app.profile);contacts={f"{r['label']} · {r['address']}":r['address'] for r in book}
    ttk.Label(frame,text='Saved contacts').pack(anchor='w');choice=ttk.Combobox(frame,values=list(contacts),state='readonly');choice.pack(fill='x',pady=5);choice.bind('<<ComboboxSelected>>',lambda e:recipient.set(contacts[choice.get()]))
    for title,var in [('Recipient Pawquanta address',recipient),('Amount in PQUA',amount),('Optional local contact label',label)]:
        ttk.Label(frame,text=title).pack(anchor='w');ttk.Entry(frame,textvariable=var).pack(fill='x',pady=5)
    ttk.Label(frame,textvariable=status,wraplength=640).pack(anchor='w',pady=10)
    def prepare():
        if app.sending:return
        app.sending=True;button.configure(state='disabled');address=recipient.get().strip();raw=amount.get();name=label.get().strip()
        def result(quote,failure):
            if failure or not window.winfo_exists():
                app.sending=False
                if window.winfo_exists():button.configure(state='normal');status.set(failure or 'Cancelled')
                return
            text=f"Send {Decimal(quote['units'])/features.UNIT:,.8f} PQUA\nTo: {quote['address']}\nNetwork fee: {quote['fee']} PQUA\nTotal wallet cost: {Decimal(quote['units'])/features.UNIT+Decimal(quote['fee']):,.8f} PQUA\n\nCheck the full address. Confirmed transfers cannot be reversed."
            if not messagebox.askyesno('Confirm transfer',text,parent=window):app.sending=False;button.configure(state='normal');status.set('Cancelled. Nothing broadcast.');return
            def transmit():
                try:
                    txid=features.confirm_send(app.runtime,app.guard,app.profile,quote)
                    if name:
                        try:features.save_contact(app.profile,name,address,app.runtime.rpc)
                        except Exception:pass
                    return txid
                finally:app.sending=False
            def done(txid,failure):
                if window.winfo_exists():button.configure(state='normal');status.set(failure or 'Broadcast: '+txid)
                app.progress(failure or 'Transfer broadcast: '+txid)
            task(app,transmit,done)
        task(app,lambda:features.prepare_send(app.runtime,app.guard,address,raw),result)
    button=ttk.Button(frame,text='Review exact fee',command=prepare);button.pack(anchor='w')


def history(app):
    window,frame=panel(app,'Wallet history and CSV export','1080x650');rows=[];offset=[0];busy=[False]
    search=tk.StringVar();status=tk.StringVar(value='Connect the wallet to load history.')
    ttk.Label(frame,text='Payments and mining rewards',style='Title.TLabel').pack(anchor='w')
    entry=ttk.Entry(frame,textvariable=search);entry.pack(fill='x',pady=8);entry.focus_set()
    table=ttk.Treeview(frame,columns=('date','type','amount','conf','txid'),show='headings')
    for key,title,width in [('date','Local date/time',155),('type','Category',95),('amount','PQUA',140),('conf','Confirmations',100),('txid','Transaction',500)]:table.heading(key,text=title);table.column(key,width=width)
    scroll=ttk.Scrollbar(frame,command=table.yview);table.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');table.pack(fill='both',expand=True)
    def display(*_):
        if not window.winfo_exists():return
        table.delete(*table.get_children());needle=search.get().casefold();matches=[r for r in rows if needle in ' '.join(str(v) for v in r.values()).casefold()]
        for r in matches[-2000:]:table.insert('',tk.END,values=(dt.datetime.fromtimestamp(r.get('time',0)).strftime('%Y-%m-%d %H:%M'),r.get('category'),str(r.get('amount')),r.get('confirmations',0),r.get('txid')))
        status.set(f'{len(rows)} loaded entries · {len(matches)} matches · showing up to 2,000. Search covers loaded pages.')
    search.trace_add('write',display)
    def load():
        if busy[0]:return
        busy[0]=True
        def done(value,failure):
            busy[0]=False
            if failure:status.set(failure);return
            rows[:0]=value;offset[0]+=len(value);display()
        task(app,lambda:connected(app).wallet('listtransactions','*',1000,offset[0],True),done)
    def export():
        file=filedialog.asksaveasfilename(parent=window,defaultextension='.csv',initialfile='Pawquanta-history.csv')
        if file:
            try:features.export_history(file,rows);status.set('Exported loaded history. No dollar prices or tax calculations were invented.')
            except Exception as exc:status.set(str(exc))
    controls=ttk.Frame(frame);controls.pack(fill='x',pady=8);ttk.Button(controls,text='Load older 1,000 entries',command=load).pack(side='left');ttk.Button(controls,text='Export loaded history CSV',command=export).pack(side='left',padx=8)
    ttk.Label(frame,textvariable=status,wraplength=980).pack(anchor='w');load()


def explorer(app):
    window,frame=panel(app,'Local blockchain explorer','1050x650');query=tk.StringVar();kind=tk.StringVar(value='Block height')
    ttk.Label(frame,text='Explore your own node',style='Title.TLabel').pack(anchor='w')
    ttk.Label(frame,text='No addresses or searches are sent to an external website. Historical transactions may require their block or a transaction index.').pack(anchor='w',pady=8)
    row=ttk.Frame(frame);row.pack(fill='x');ttk.Combobox(row,textvariable=kind,values=['Block height','Block hash','Wallet transaction'],state='readonly',width=22).pack(side='left');ttk.Entry(row,textvariable=query).pack(side='left',fill='x',expand=True,padx=8)
    text=tk.Text(frame,wrap='word',bg='#0c1420',fg='#dce9f5');text.pack(fill='both',expand=True,pady=12)
    def lookup():
        selection=kind.get();value=query.get().strip()
        def work():
            runtime=connected(app)
            if selection=='Block height':
                if not value.isdigit():raise ValueError('Enter a non-negative block height')
                return runtime.rpc('getblock',runtime.rpc('getblockhash',int(value)),1)
            if len(value)!=64 or any(c not in '0123456789abcdefABCDEF' for c in value):raise ValueError('Enter a 64-character transaction or block hash')
            return runtime.rpc('getblock',value,1) if selection=='Block hash' else runtime.wallet('gettransaction',value)
        def done(value,failure):
            if window.winfo_exists():text.delete('1.0','end');text.insert('end',failure or json.dumps(value,indent=2,default=str))
        task(app,work,done)
    ttk.Button(row,text='Look up',command=lookup).pack(side='right')


def backups(app):
    window,frame=panel(app,'Encrypted backup and recovery','800x530');status=tk.StringVar(value='Keep the bundle and its passphrase separately. Losing both wallet copies and recovery credentials can lose access to coins.')
    ttk.Label(frame,text='Backup and recovery',style='Title.TLabel').pack(anchor='w')
    ttk.Label(frame,text='The bundle encrypts your wallet backup, recovery password, receiving address, saved mining limit and reward ledger together. Use a strong, unique passphrase.',wraplength=750).pack(anchor='w',pady=12)
    def password():return simpledialog.askstring('Backup passphrase','Backup passphrase (at least 12 characters):',show='*',parent=window)
    def result(value,failure):
        if window.winfo_exists():status.set(failure or value)
    def create():
        if not app.runtime:error(app,'Connect first so the native wallet can create a consistent backup.');return
        file=filedialog.asksaveasfilename(parent=window,defaultextension='.pquabackup',initialfile='Pawquanta-'+time.strftime('%Y%m%d-%H%M%S')+'.pquabackup')
        if not file:return
        secret=password()
        if not secret:return
        repeated=simpledialog.askstring('Confirm passphrase','Repeat your backup passphrase:',show='*',parent=window)
        if secret!=repeated:status.set('Passphrases did not match.');return
        status.set('Creating and verifying encrypted bundle…')
        task(app,lambda:(features.make_backup(app.runtime,app.profile,secret,file) and 'Backup created and authenticated successfully: '+file),result)
    def read(restore=False):
        file=filedialog.askopenfilename(parent=window,filetypes=[('Pawquanta encrypted backup','*.pquabackup')])
        if not file:return
        secret=password()
        if not secret:return
        parent=filedialog.askdirectory(parent=window,title='Choose a parent folder for a NEW restored wallet') if restore else None
        if restore and not parent:return
        def work():
            try:body=features.read_backup(file,secret)
            except Exception:raise ValueError('Backup could not be authenticated. Check its passphrase and file integrity.')
            if not restore:return f"Backup authenticated. Receiving address: {body['address']}\nTo verify native wallet recovery, restore into a new folder and connect it."
            destination=Path(parent)/('Pawquanta-Restored-'+time.strftime('%Y%m%d-%H%M%S'))
            features.restore_backup(body,destination)
            return {'message':'Restored separately to '+str(destination)+'. Use Open restored wallet to connect it. Mining starts stopped.','destination':str(destination)}
        def done(value,failure):
            result(value['message'] if isinstance(value,dict) else value,failure)
            if not failure and restore:app.restore_candidate=Path(value['destination'])
        task(app,work,done)
    def open_restored():
        path=getattr(app,'restore_candidate',None)
        if not path:status.set('Restore a bundle into a new folder first.');return
        if app.sending:status.set('Finish the current wallet transaction first.');return
        if messagebox.askyesno('Open restored wallet','Safely close this wallet and open the separate restored profile? Mining will remain stopped.',parent=window):app.pending_restore=path;app.close()
    for label,command in [('Create encrypted bundle',create),('Verify bundle integrity',lambda:read(False)),('Restore into a new folder',lambda:read(True)),('Open restored wallet',open_restored)]:ttk.Button(frame,text=label,command=command).pack(anchor='w',pady=6)
    ttk.Label(frame,textvariable=status,wraplength=750).pack(anchor='w',pady=14)


def plan(app):
    from mining_plan import save,cancel
    window,frame=panel(app,'Mining schedule and limits','730x490');start=tk.StringVar(value=dt.datetime.now().strftime('%Y-%m-%d %H:%M'));duration=tk.StringVar(value='60');cap=tk.StringVar(value='1260000');status=tk.StringVar()
    try:cap.set(str(Decimal(json.loads((app.profile/'mining-preferences.json').read_text())['limit_atomic_units'])/features.UNIT))
    except (OSError,ValueError,KeyError):pass
    ttk.Label(frame,text='Plan one mining session',style='Title.TLabel').pack(anchor='w')
    ttk.Label(frame,text='The wallet must remain open and the computer awake. A missed or expired session will not mine retroactively.',wraplength=670).pack(anchor='w',pady=10)
    for title,var in [('Start in this computer’s local time (YYYY-MM-DD HH:MM)',start),('Duration in minutes',duration),('Cumulative personal mined-reward ceiling (PQUA)',cap)]:ttk.Label(frame,text=title).pack(anchor='w');ttk.Entry(frame,textvariable=var).pack(fill='x',pady=6)
    def apply():
        try:
            connected(app);limit=features.amount_units(cap.get());stamp=dt.datetime.strptime(start.get(),'%Y-%m-%d %H:%M').timestamp();minutes=int(duration.get())
            from mining_schedule import cancel as cancel_pause
            cancel_pause(app.profile);app.stop_mining(cancel_schedule=False);save(app.profile,stamp,minutes)
            features.atomic_json(app.profile/'mining-preferences.json',{'limit_atomic_units':limit,'gpu':app.gpu.get()});status.set('Session armed. The existing cumulative reward ledger is retained.')
        except Exception as exc:status.set(str(exc))
    ttk.Button(frame,text='Arm session',command=apply).pack(anchor='w',pady=6)
    ttk.Button(frame,text='Cancel planned session',command=lambda:(cancel(app.profile),status.set('Planned session cancelled.'))).pack(anchor='w')
    ttk.Label(frame,textvariable=status,wraplength=670).pack(anchor='w',pady=10)


def contacts(app):
    window,frame=panel(app,'Local address book','850x520');label=tk.StringVar();address=tk.StringVar();status=tk.StringVar()
    table=ttk.Treeview(frame,columns=('label','address'),show='headings');table.heading('label',text='Local label');table.heading('address',text='Pawquanta address');table.column('label',width=200);table.column('address',width=600);table.pack(fill='both',expand=True)
    def load():
        table.delete(*table.get_children())
        for row in features.address_book(app.profile):table.insert('',tk.END,values=(row['label'],row['address']))
    for title,var in [('Label',label),('Address',address)]:ttk.Label(frame,text=title).pack(anchor='w');ttk.Entry(frame,textvariable=var).pack(fill='x',pady=4)
    def add():
        name,value=label.get(),address.get().strip()
        def done(result,failure):
            if window.winfo_exists():status.set(failure or 'Contact saved locally.');load()
        task(app,lambda:features.save_contact(app.profile,name,value,connected(app).rpc),done)
    ttk.Button(frame,text='Validate and save contact',command=add).pack(anchor='w',pady=6);ttk.Label(frame,textvariable=status).pack(anchor='w');load()


def build_shell(app):
    notebook=ttk.Notebook(app.window);notebook.pack(fill='both',expand=True,padx=10,pady=8);app.notebook=notebook
    dashboard=ttk.Frame(notebook);tools=ttk.Frame(notebook,padding=20);checks=ttk.Frame(notebook,padding=20);settings=ttk.Frame(notebook,padding=20)
    for page,title in [(dashboard,'Dashboard'),(tools,'Wallet tools'),(checks,'Connection doctor'),(settings,'Settings & recovery')]:notebook.add(page,text=title)
    canvas=tk.Canvas(dashboard,highlightthickness=0,bg='#111820');scroll=ttk.Scrollbar(dashboard,orient='vertical',command=canvas.yview);canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
    frame=ttk.Frame(canvas,padding=24);item=canvas.create_window((0,0),window=frame,anchor='nw')
    frame.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')));canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
    app.telemetry=tk.StringVar(value='Live compute: waiting for a fresh mining sample.');app.session_info=tk.StringVar(value='Mining session: not scheduled.');app.last_snapshot=None
    ttk.Label(tools,text='Your wallet workspace',style='Title.TLabel').pack(anchor='w')
    for title,fn,description in [('History and CSV export',history,'Search loaded transaction pages and export amounts, fees and confirmations.'),('Receive with QR code',receive,'Share a Pawquanta address without visiting a QR-code website.'),('Local address book',contacts,'Save labels and validated addresses on this computer.'),('Local blockchain explorer',explorer,'Inspect blocks and wallet transactions using your node.'),('Encrypted backup and recovery',backups,'Create authenticated bundles and restore into a new folder.'),('Mining schedule and limits',plan,'Choose a start, duration and cumulative reward ceiling.')]:
        ttk.Button(tools,text=title,command=lambda f=fn:f(app)).pack(anchor='w',pady=(12,3));ttk.Label(tools,text=description,wraplength=740).pack(anchor='w')
    ttk.Label(checks,text='Connection doctor',style='Title.TLabel').pack(anchor='w');table=ttk.Treeview(checks,columns=('area','state','action'),show='headings',height=12)
    for key,title,width in [('area','Component',120),('state','Status',180),('action','Next step',500)]:table.heading(key,text=title);table.column(key,width=width)
    table.pack(fill='both',expand=True,pady=12);diagnostic=tk.StringVar(value='Checks read your local state. They never reset a wallet or remove coins.');ttk.Label(checks,textvariable=diagnostic,wraplength=760).pack(anchor='w')
    def diagnose():
        compute={}
        try:compute=json.loads((app.profile/'pdcrm-status.json').read_text());stale=time.time()-compute.get('updated_at',0)>10
        except (OSError,ValueError):stale=True
        if stale:compute={}
        table.delete(*table.get_children())
        guard=app.guard.state if app.guard else None
        for row in features.diagnosis(app.last_snapshot,compute,bool(app.worker and app.worker.is_alive()),app.stop_file.exists(),guard):table.insert('',tk.END,values=row)
        diagnostic.set('Compute sample is stale or absent; do not interpret it as current hashing.' if stale else 'Local checks refreshed. Temperature protection depends on functioning sensors.')
    def retry():
        if not app.runtime:
            if not app.connection_worker or not app.connection_worker.is_alive():app.connect()
            return
        diagnostic.set('Requesting a seed connection. Tor may take time to establish it.')
        def done(value,failure):diagnostic.set(failure or 'Seed retry requested. Watch peer count on the dashboard.');diagnose()
        task(app,lambda:app.runtime.rpc('addnode',app.manifest['seed_nodes'][0],'onetry'),done)
    row=ttk.Frame(checks);row.pack(fill='x',pady=10)
    for title,fn in [('Run checks',diagnose),('Retry seed connection',retry),('CPU temperature setup',app.cpu_setup)]:ttk.Button(row,text=title,command=fn).pack(side='left',padx=5)
    ttk.Label(settings,text='Preferences and recovery',style='Title.TLabel').pack(anchor='w');prefs=features.preferences(app.profile)
    motion=tk.BooleanVar(value=prefs['reduced_motion']);theme=tk.StringVar(value=prefs['theme']);scale=tk.StringVar(value=str(prefs['text_scale'])+'%')
    ttk.Checkbutton(settings,text='Reduced motion — skip startup animation',variable=motion).pack(anchor='w',pady=12)
    ttk.Label(settings,text='Theme').pack(anchor='w');ttk.Combobox(settings,textvariable=theme,values=['dark','light'],state='readonly',width=20).pack(anchor='w',pady=5)
    ttk.Label(settings,text='Interface text size').pack(anchor='w');ttk.Combobox(settings,textvariable=scale,values=['100%','120%','140%'],state='readonly',width=20).pack(anchor='w',pady=5)
    def apply():
        app.profile.mkdir(parents=True,exist_ok=True);features.atomic_json(app.profile/'wallet-ui.json',{'reduced_motion':motion.get(),'theme':theme.get(),'text_scale':int(scale.get().rstrip('%'))});style=ttk.Style();light=theme.get()=='light';bg='#f2f5f8' if light else '#111820';fg='#112334' if light else '#edf1f4';size=round(11*int(scale.get().rstrip('%'))/100)
        style.configure('TFrame',background=bg);style.configure('TLabel',background=bg,foreground=fg,font=('Segoe UI',size));style.configure('TButton',font=('Segoe UI',size));canvas.configure(bg=bg)
    ttk.Button(settings,text='Apply preferences',command=apply).pack(anchor='w',pady=10)
    health=tk.StringVar(value='Startup verified when the dashboard opens.');ttk.Label(settings,textvariable=health,wraplength=760).pack(anchor='w',pady=10)
    def health_check():
        from core_runtime import file_hash
        try:
            matched=file_hash(app.manifest_path())==app.manifest['windows_node_sha256']
            health.set('Packaged native node hash: '+('matches manifest' if matched else 'MISMATCH — do not connect')+'\nInstalled wallet: '+__import__('wallet_updates').VERSION+'\nAuto-update: '+('enabled' if app.auto_update.get() else 'disabled'))
        except Exception as exc:health.set('Health check needs attention: '+str(exc))
    def update_now():
        if not app.updates:health.set('Updates unavailable in this test or source environment.');return
        def done(value,failure):
            health.set(failure or ('Approved update '+value['version']+' ready.' if value else 'No newer approved update.'))
            if value:app.events.put(('update_ready',value))
        task(app,app.updates.check,done)
    ttk.Button(settings,text='Check installation health',command=health_check).pack(anchor='w',pady=5);ttk.Button(settings,text='Check signed updates now',command=update_now).pack(anchor='w',pady=5)
    ttk.Label(settings,text='Recovery: keep encrypted backup bundles and passphrases separately. Restore into a fresh folder. If startup fails, use a verified release package with the same wallet profile; never delete the profile to fix an installation. The updater refuses unverified packages and protocol changes.',wraplength=760).pack(anchor='w',pady=12)
    ttk.Label(settings,text='Keyboard: Ctrl+1…4 selects a section. Ctrl+F opens searchable history. F5 refreshes diagnostics. Mining schedules require the wallet open and the computer awake.',wraplength=760).pack(anchor='w',pady=8)
    for index in range(4):app.window.bind('<Control-Key-'+str(index+1)+'>',lambda e,i=index:notebook.select(i))
    app.window.bind('<Control-f>',lambda e:history(app));app.window.bind('<F5>',lambda e:(notebook.select(2),diagnose()))
    app.refresh_diagnostics=diagnose
    ttk.Style().configure('TLabel',font=('Segoe UI',round(11*prefs['text_scale']/100)))
    ttk.Style().configure('TButton',font=('Segoe UI',round(11*prefs['text_scale']/100)))
    if prefs['theme']=='light':
        ttk.Style().configure('TFrame',background='#f2f5f8');ttk.Style().configure('TLabel',background='#f2f5f8',foreground='#112334');canvas.configure(bg='#f2f5f8')
    return frame
