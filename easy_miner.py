"""Pawquanta desktop research edition. No Python install needed in the packaged EXE."""
import copy
import json
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import time
import webbrowser
import pawquanta as p
from cryptography.hazmat.primitives import serialization

def self_test():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); password='disposable-packaging-test'
        miner=p.new_wallet(root/'wallet.pem',password)
        recipient=p.new_wallet(root/'recipient.pem',password)
        node=p.Node(root/'chain.json',token=secrets.token_urlsafe(32))
        for _ in range(4): node.accept_chain(node.chain+[p.mine(node.chain,miner)])
        tx=p.sign(p.load_wallet(root/'wallet.pem',password),recipient,10*p.UNIT,0)
        node.add_tx(tx)
        node.accept_chain(node.chain+[p.mine(node.chain,miner,node.pool)])
        assert node.status()['balances'][recipient]==10*p.UNIT
        assert p.Node(root/'chain.json').status()['tip']==node.status()['tip']
        (Path(sys.executable).parent/'self-test-result.json' if getattr(sys,'frozen',False) else root/'result.json').write_text(json.dumps({'passed':True,'height':node.status()['height'],'checks':['encrypted wallet','mining','signed payment','persistence']}))

def main():
    import tkinter as tk
    from tkinter import messagebox, simpledialog, ttk
    root=tk.Tk(); root.title('Pawquanta · Research Edition'); root.geometry('740x600'); root.minsize(620,540)
    root.configure(bg='#131821')
    style=ttk.Style(); style.theme_use('clam')
    style.configure('TFrame',background='#131821'); style.configure('TLabel',background='#131821',foreground='#eee',font=('Segoe UI',11))
    style.configure('TButton',font=('Segoe UI',11),padding=9)
    folder=(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent)/'Pawquanta-data'
    folder.mkdir(exist_ok=True)
    node=p.Node(folder/'chain.json',token=secrets.token_urlsafe(32)); server=p.Server(('127.0.0.1',0),node)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url='http://127.0.0.1:'+str(server.server_port)
    wallet=folder/'wallet.pem'; mining=threading.Event(); stop=threading.Event()
    address_var=tk.StringVar(value=(folder/'address.txt').read_text() if (folder/'address.txt').exists() else 'Create a wallet to begin.')
    status_var=tk.StringVar(value='Ready. This is a local practice network.')
    height_var=tk.StringVar()
    frame=ttk.Frame(root,padding=25); frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='Pawquanta / PQUA',font=('Segoe UI',25,'bold')).pack(anchor='w')
    ttk.Label(frame,text='RESEARCH EDITION · TEST COINS HAVE NO MONETARY VALUE',foreground='#ffb477',font=('Segoe UI',10,'bold')).pack(anchor='w',pady=(6,20))
    ttk.Label(frame,text='1. Create your wallet   2. Mine practice coins   3. Try a payment',wraplength=650).pack(anchor='w',pady=(0,15))
    ttk.Label(frame,text='Your receiving address').pack(anchor='w')
    entry=ttk.Entry(frame,textvariable=address_var,state='readonly',font=('Consolas',10)); entry.pack(fill='x',pady=(8,8))
    ttk.Label(frame,textvariable=height_var).pack(anchor='w',pady=(6,10))
    buttons=ttk.Frame(frame); buttons.pack(fill='x',pady=8)
    def show_error(exc): root.after(0,lambda:messagebox.showerror('Pawquanta',str(exc),parent=root))
    def create_wallet():
        if wallet.exists(): messagebox.showinfo('Wallet exists','Your wallet already exists. Back it up together with its password.'); return
        password=simpledialog.askstring('Create wallet','Choose a password (at least 12 characters):',show='*',parent=root)
        if password is None:return
        confirm=simpledialog.askstring('Create wallet','Type the same password again:',show='*',parent=root)
        if confirm!=password:messagebox.showerror('Passwords differ','Please try again.');return
        try:
            addr=p.new_wallet(wallet,password);(folder/'address.txt').write_text(addr);address_var.set(addr)
            status_var.set('Wallet created. Back up the wallet file and remember its password.')
        except Exception as exc:show_error(exc)
    def mine():
        if not wallet.exists():messagebox.showinfo('Create wallet first','Click Create wallet before mining.');return
        if mining.is_set():return
        mining.set();stop.clear();status_var.set('Mining up to 4 blocks. Stop is available at any time.')
        # Resolve UI data on the main thread, before starting a worker.
        miner=address_var.get()
        def safe_work():
            try:
                for _ in range(4):
                    if stop.is_set():break
                    with node.lock:chain=copy.deepcopy(node.chain);pool=copy.deepcopy(node.pool)
                    node.accept_chain(chain+[p.mine(chain,miner,pool)])
                    if stop.wait(1):break
                root.after(0,lambda:status_var.set('Mining stopped. You can mine another 4 blocks when ready.'))
            except Exception as exc:show_error(exc)
            finally:mining.clear()
        threading.Thread(target=safe_work,daemon=True).start()
    def send():
        if not wallet.exists():messagebox.showinfo('Create wallet first','Create a wallet first.');return
        to=simpledialog.askstring('Send practice coins','Receiving PQUA address:',parent=root)
        if not to:return
        amount=simpledialog.askstring('Send practice coins','Amount in PQUA (for example, 1.5):',parent=root)
        if not amount:return
        password=simpledialog.askstring('Unlock wallet','Wallet password:',show='*',parent=root)
        if password is None:return
        try:
            from decimal import Decimal,InvalidOperation
            value=Decimal(amount)*p.UNIT
            if not value.is_finite() or value!=int(value) or value<=0:raise ValueError('Use a positive amount with up to 8 decimal places.')
            key=p.load_wallet(wallet,password);src=address_var.get();state=node.status()
            nonce=state['next_nonces'].get(src,0)+sum(tx['from']==src for tx in node.pool)
            node.add_tx(p.sign(key,to,int(value),nonce));status_var.set('Payment queued. Mine a block to confirm it on this local network.')
        except Exception as exc:show_error(exc)
    ttk.Button(buttons,text='Create wallet',command=create_wallet).pack(side='left',padx=(0,8))
    ttk.Button(buttons,text='Mine 4 blocks',command=mine).pack(side='left',padx=(0,8))
    ttk.Button(buttons,text='Stop',command=stop.set).pack(side='left',padx=(0,8))
    ttk.Button(buttons,text='Send coins',command=send).pack(side='left')
    ttk.Button(frame,text='Open explorer',command=lambda:webbrowser.open(url)).pack(anchor='w',pady=8)
    ttk.Label(frame,textvariable=status_var,wraplength=650,foreground='#ffb477').pack(anchor='w',pady=(15,12))
    ttk.Label(frame,text='This download runs your own local research network. It does not connect to a public mainnet. Other people’s separate local copies do not share your balances. No internet ports are opened.',wraplength=650).pack(anchor='w',pady=10)
    ttk.Label(frame,text='Your data: '+str(folder)+'\nBack up wallet.pem and keep your password separately. First rewards become spendable after 3 more blocks.',wraplength=650,font=('Segoe UI',9),foreground='#a3a6ac').pack(anchor='w',pady=10)
    def refresh():
        state=node.status();balance=state['balances'].get(address_var.get(),0)/p.UNIT
        height_var.set(f"Block {state['height']}    Available: {balance:.8f} PQUA    Pending payments: {state['mempool']}")
        root.after(1500,refresh)
    def close():stop.set();server.shutdown();server.server_close();root.destroy()
    root.protocol('WM_DELETE_WINDOW',close);refresh();root.mainloop()

if __name__=='__main__':
    if '--self-test' in sys.argv:self_test()
    else:main()
