"""Pinned official Tor download and private desktop client. SPDX-License-Identifier: MIT"""
import hashlib
import os
from pathlib import Path,PurePosixPath
import shutil
import socket
import subprocess
import tarfile
import time
from core_runtime import free_port,private_directory

TOR_URL='https://dist.torproject.org/torbrowser/15.0.25/tor-expert-bundle-windows-x86_64-15.0.25.tar.gz'
TOR_SHA256='c1988c701de2f24f7d098d1d6d7f507b58f27740d097f29c246e0524d639b252'

class TorClient:
    def __init__(self,directory,status=lambda message:None):
        self.directory=Path(directory).resolve();self.status=status
        self.port,self.control=free_port(),free_port()
        self.process=self.log=None

    def start(self):
        if os.name!='nt':raise ValueError('Desktop transport package currently supports Windows x64')
        private_directory(self.directory)
        tools=self.directory/'tools';binary=tools/'tor/tor.exe'
        if not binary.exists():
            self.status('Downloading the verified network connection (about 23 MB)…')
            archive=self.directory/'tor-official.tar.gz'
            temporary=archive.with_suffix('.download')
            subprocess.run(['curl.exe','--fail','--location','--silent','--show-error','--retry','2',
                '--max-time','180','--max-filesize','67108864','--output',str(temporary),TOR_URL],check=True,
                creationflags=subprocess.CREATE_NO_WINDOW)
            with temporary.open('rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=TOR_SHA256:
                    raise ValueError('Network download failed verification; it was not executed')
            temporary.replace(archive)
            tools.mkdir(exist_ok=True)
            with tarfile.open(archive) as source:
                for member in source.getmembers():
                    path=PurePosixPath(member.name)
                    if path.is_absolute() or '..' in path.parts or member.issym() or member.islnk():
                        raise ValueError('Unsupported network archive path')
                    output=tools.joinpath(*path.parts)
                    if member.isdir():output.mkdir(parents=True,exist_ok=True)
                    elif member.isfile():
                        output.parent.mkdir(parents=True,exist_ok=True)
                        with source.extractfile(member) as incoming,output.open('wb') as outgoing:
                            shutil.copyfileobj(incoming,outgoing)
                    else:raise ValueError('Unsupported network archive entry')
        state=self.directory/'state';state.mkdir(exist_ok=True)
        def quoted(path):return '"'+str(path).replace('\\','/')+'"'
        config=self.directory/'torrc'
        config.write_text(f'DataDirectory {quoted(state)}\nSocksPort 127.0.0.1:{self.port}\n'
            f'ControlPort 127.0.0.1:{self.control}\nCookieAuthentication 1\n'
            f'CookieAuthFile {quoted(self.directory / "control-cookie")}\n'
            'ClientOnly 1\nExitRelay 0\nAvoidDiskWrites 1\nSafeLogging 1\nLog notice stdout\n')
        self.log=(self.directory/'transport.log').open('wb')
        self.process=subprocess.Popen([str(binary),'-f',str(config)],stdout=self.log,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW)
        deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            if self.process.poll() is not None:raise RuntimeError('Network connection stopped; see the private transport.log')
            text=(self.directory/'transport.log').read_text(errors='replace')[-16384:]
            if 'Bootstrapped 100%' in text:
                self.status('Private network connection ready');return
            lines=[line for line in text.splitlines() if 'Bootstrapped ' in line]
            if lines:self.status(lines[-1].split('[notice]')[-1].strip())
            time.sleep(1)
        raise TimeoutError('Network connection is taking longer than expected; retry when internet is available')

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            try:
                cookie=(self.directory/'control-cookie').read_bytes().hex()
                with socket.create_connection(('127.0.0.1',self.control),timeout=5) as connection:
                    stream=connection.makefile('rwb',buffering=0)
                    stream.write(('AUTHENTICATE '+cookie+'\r\n').encode())
                    if not stream.readline().startswith(b'250'):raise RuntimeError('Transport authentication failed')
                    stream.write(b'SIGNAL SHUTDOWN\r\n')
                    if not stream.readline().startswith(b'250'):raise RuntimeError('Transport shutdown failed')
                self.process.wait(timeout=20)
            except (OSError,RuntimeError,subprocess.TimeoutExpired):return False
        if self.log:self.log.close();self.log=None
        return True

    def connect(self,host,port):
        import re
        if not re.fullmatch('[a-z2-7]{56}\\.onion',host):raise ValueError('Expected a v3 onion service')
        connection=socket.create_connection(('127.0.0.1',self.port),timeout=45)
        def receive(size):
            data=b''
            while len(data)<size:
                part=connection.recv(size-len(data))
                if not part:raise OSError('Private connection closed')
                data+=part
            return data
        try:
            connection.sendall(b'\x05\x01\x00')
            if receive(2)!=b'\x05\x00':raise OSError('SOCKS negotiation failed')
            name=host.encode();connection.sendall(b'\x05\x01\x00\x03'+bytes([len(name)])+name+port.to_bytes(2,'big'))
            result=receive(4)
            if result[1]!=0:raise OSError('Public service could not be reached: SOCKS '+str(result[1]))
            receive(4 if result[3]==1 else 16 if result[3]==4 else receive(1)[0]);receive(2)
            return connection
        except BaseException:connection.close();raise
