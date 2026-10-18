"""Use the same pinned header-only Boost version as the verified Linux build."""
import hashlib
from pathlib import Path
import subprocess
import urllib.request
root=Path.cwd()/'boost-pinned';root.mkdir(exist_ok=True)
archive=root/'boost.tar.gz'
urllib.request.urlretrieve('https://archives.boost.io/release/1.88.0/source/boost_1_88_0.tar.gz',archive)
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='3621533e820dcab1e8012afd583c0c73cf0f77694952b81352bf38c1488f9cb4'
subprocess.run(['tar','-xzf',str(archive),'-C',str(root)],check=True)
config=root/'cmake';config.mkdir(exist_ok=True)
(config/'BoostConfig.cmake').write_text('set(Boost_FOUND TRUE)\nset(Boost_VERSION 1.88.0)\nadd_library(Boost::headers INTERFACE IMPORTED)\nset_target_properties(Boost::headers PROPERTIES INTERFACE_INCLUDE_DIRECTORIES "'+str(root/'boost_1_88_0')+'")\n')
(config/'BoostConfigVersion.cmake').write_text('set(PACKAGE_VERSION 1.88.0)\nif(PACKAGE_FIND_VERSION VERSION_GREATER PACKAGE_VERSION)\nset(PACKAGE_VERSION_COMPATIBLE FALSE)\nelse()\nset(PACKAGE_VERSION_COMPATIBLE TRUE)\nendif()\n')
