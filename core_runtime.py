"""Private desktop node/wallet controller for the separately packaged Core backend."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
from core_miner import RPC

MAIN_GENESIS = '00000037ccad3f09210835664fce3f8d4ff283e308d8a6cece13e1b4d4d63580'
LAUNCH_EPOCH = 1792335600


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def free_port():
    with socket.socket() as stream:
        stream.bind(('127.0.0.1', 0))
        return stream.getsockname()[1]


def private_directory(path):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        identity = subprocess.check_output(['whoami.exe'], text=True,
            creationflags=subprocess.CREATE_NO_WINDOW).strip()
        subprocess.run(['icacls.exe', str(path), '/inheritance:r', '/grant:r',
            identity + ':(OI)(CI)F', 'SYSTEM:(OI)(CI)F'], check=True,
            stdout=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        path.chmod(0o700)
    return path


class CoreRuntime:
    """Own only newly started child processes and a dedicated Pawquanta data directory.

    Ordinary clients have no public listener. The owner connects to the VM through
    loopback. Other desktop clients use the bundled Tor connection and public seed.
    """
    def __init__(self, directory, binary, expected_sha256, genesis=MAIN_GENESIS,
                 development=False, seed=None, socks_port=None, status=lambda message: None):
        self.binary = Path(binary).resolve()
        if not expected_sha256 or len(expected_sha256) != 64 or file_hash(self.binary) != expected_sha256:
            raise ValueError('The node program does not match the verified package')
        if not development and genesis != MAIN_GENESIS:
            raise ValueError('Pawquanta public-network identity does not match')
        requested_directory = Path(directory).resolve()
        marker = requested_directory / '.pawquanta-runtime.json'
        identity = {'genesis': genesis, 'development': bool(development), 'schema': 1}
        if requested_directory.exists() and any(requested_directory.iterdir()):
            if not marker.is_file() or json.loads(marker.read_text()) != identity:
                raise ValueError('Existing folder is not this Pawquanta runtime; its files were preserved')
        self.directory = private_directory(requested_directory)
        if not marker.exists():
            with marker.open('x',encoding='utf-8') as output:
                json.dump(identity,output)
        if seed and not seed.startswith('127.0.0.1:'):
            import re
            if not re.fullmatch('[a-z2-7]{56}\\.onion:18731', seed) or not socks_port:
                raise ValueError('Public seed requires the pinned onion address and local Tor proxy')
        self.genesis, self.development = genesis, development
        self.seed, self.socks_port, self.status = seed, socks_port, status
        self.process = self.rpc = self.wallet = self.log = None
        self._lock_context = None

    def start(self):
        from core_miner import exclusive_miner
        self._lock_context = exclusive_miner(self.directory / 'desktop-node')
        self._lock_context.__enter__()
        try:
            data = self.directory / 'node'
            data.mkdir(exist_ok=True)
            identity_file = self.directory / 'network.json'
            identity = {'genesis': self.genesis, 'chain': 'regtest' if self.development else 'main'}
            if identity_file.exists():
                if json.loads(identity_file.read_text()) != identity:
                    raise ValueError('This folder belongs to a different network; choose a separate folder')
            else:
                # Never adopt arbitrary pre-existing node/wallet files.
                if any(data.iterdir()):
                    raise ValueError('Unrecognized existing node directory; existing files were preserved')
                identity_file.write_text(json.dumps(identity, indent=2) + '\n')
            port = free_port()
            args = [str(self.binary), '-chain=' + identity['chain'], f'-datadir={data}',
                '-server=1', '-rpcbind=127.0.0.1', '-rpcallowip=127.0.0.1', f'-rpcport={port}',
                '-listen=0', '-listenonion=0', '-discover=0', '-dnsseed=0', '-fixedseeds=0',
                '-natpmp=0', '-dbcache=64', '-maxmempool=32', '-maxconnections=16', '-par=2',
                '-fallbackfee=0.00001']
            if self.seed:
                args.append('-addnode=' + self.seed)
            elif self.development:
                args.append('-connect=0')
            else:
                raise ValueError('Public peer connection is not configured')
            if self.socks_port:
                args += [f'-proxy=127.0.0.1:{int(self.socks_port)}', '-onlynet=onion']
            self.log = (self.directory / 'node-process.log').open('ab')
            self.process = subprocess.Popen(args, stdout=self.log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            cookie = data / ('regtest/.cookie' if self.development else '.cookie')
            self.rpc = RPC(f'http://127.0.0.1:{port}', cookie)
            self.status('Starting your private node…')
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError('Node stopped during startup; see the private node-process.log')
                try:
                    info = self.rpc('getblockchaininfo')
                    if info['chain'] != identity['chain'] or self.rpc('getblockhash', 0) != self.genesis:
                        raise ValueError('Live node identity differs from the package')
                    self.status('Node started on the verified network')
                    return info
                except (OSError, RuntimeError):
                    time.sleep(0.25)
            raise TimeoutError('The node did not finish startup')
        except BaseException:
            self.stop()
            raise

    def open_wallet(self, name='wallet'):
        """Create an encrypted wallet once; keep its generated password private locally."""
        import urllib.parse
        if name not in ('wallet', 'owner'):
            raise ValueError('Unexpected wallet name')
        password_file = self.directory / (name + '-recovery-password.txt')
        existing = [wallet['name'] for wallet in self.rpc('listwalletdir')['wallets']]
        if name not in existing:
            if password_file.exists():
                raise ValueError('Recovery password exists without its wallet; preserve it and restore the wallet')
            password = secrets.token_urlsafe(32)
            # Persist the recovery password before wallet creation. Never print it.
            with password_file.open('x', encoding='utf-8') as output:
                output.write(password + '\n')
                output.flush()
                os.fsync(output.fileno())
            if os.name != 'nt':
                password_file.chmod(0o600)
            self.rpc('createwallet', name, False, False, password, False, True, True)
        elif name not in self.rpc('listwallets'):
            self.rpc('loadwallet', name, True)
        self.wallet = RPC(self.rpc.url + '/wallet/' + urllib.parse.quote(name, safe=''), self.rpc.cookie)
        info = self.wallet('getwalletinfo')
        if 'unlocked_until' not in info:
            raise ValueError('The receiving wallet is not encrypted')
        address_file = self.directory / (name + '-receiving-address.txt')
        if address_file.exists():
            address = address_file.read_text().strip()
            if not self.wallet('getaddressinfo', address).get('ismine'):
                raise ValueError('Saved receiving address is not owned by this wallet')
        else:
            address = self.wallet('getnewaddress', 'mining', 'bech32')
            address_file.write_text(address + '\n')
        # A second encrypted copy is ready for the user to move to separate storage.
        backup = self.directory / (name + '-encrypted-backup.dat')
        self.wallet('backupwallet', str(backup))
        self.status('Encrypted wallet and backup ready')
        return address

    def snapshot(self):
        chain = self.rpc('getblockchaininfo')
        network = self.rpc('getnetworkinfo')
        balances = self.wallet('getbalances')['mine'] if self.wallet else {}
        return {'height': chain['blocks'], 'headers': chain['headers'],
                'synchronizing': chain['initialblockdownload'] or chain['blocks']<chain['headers'], 'peers': network['connections'],
                'spendable': str(balances.get('trusted', 0)),
                'maturing': str(balances.get('immature', 0)), 'tip': chain['bestblockhash']}

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            try:
                self.rpc('stop')
                self.process.wait(timeout=45)
            except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
                # Preserve a busy node; never terminate unrelated processes or force disk shutdown.
                self.status('Node is still shutting down; its files have been preserved')
                return False
        if self.log:
            self.log.close()
            self.log = None
        if self._lock_context:
            self._lock_context.__exit__(None, None, None)
            self._lock_context = None
        return True
