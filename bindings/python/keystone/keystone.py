# Keystone Python bindings, by Nguyen Anh Quynnh <aquynh@gmail.com>
import sys
_python2 = sys.version_info[0] < 3
if _python2:
    range = xrange

from . import arm_const, arm64_const, mips_const, sparc_const, hexagon_const, ppc_const, systemz_const, x86_const, evm_const
from .keystone_const import *

from ctypes import *
from platform import system
from os.path import split, join, dirname, exists, abspath
import sys
import os


import inspect
if not hasattr(sys.modules[__name__], '__file__'):
    __file__ = inspect.getfile(inspect.currentframe())

# Get the directory where this module is located
_lib_path = abspath(dirname(__file__))

# Define library names for each platform
_system = system()
if _system == 'Darwin':
    _lib_patterns = ['libkeystone.dylib', 'libkeystone.*.dylib']
elif _system == 'Windows':
    _lib_patterns = ['keystone.dll']
else:  # Linux and others
    _lib_patterns = ['libkeystone.so', 'libkeystone.so.*']

# Try to load the library
_ks = None
_found = False

# First, try to load from the module directory (for pip installed packages)
for pattern in _lib_patterns:
    # Direct file name
    lib_file = join(_lib_path, pattern)
    if exists(lib_file):
        try:
            _ks = cdll.LoadLibrary(lib_file)
            _found = True
            break
        except OSError:
            pass
    
    # Also try with glob pattern matching for versioned libraries
    import glob
    for lib_file in glob.glob(join(_lib_path, pattern)):
        try:
            _ks = cdll.LoadLibrary(lib_file)
            _found = True
            break
        except OSError:
            pass
    
    if _found:
        break

# If not found in module directory, try system paths
if not _found:
    # Standard library names without path
    _standard_libs = []
    if _system == 'Darwin':
        _standard_libs = ['libkeystone.dylib']
    elif _system == 'Windows':
        _standard_libs = ['keystone.dll']
    else:
        _standard_libs = ['libkeystone.so', 'libkeystone.so.%u' % KS_API_MAJOR]
    
    for lib_name in _standard_libs:
        try:
            _ks = cdll.LoadLibrary(lib_name)
            _found = True
            break
        except OSError:
            pass

# Try common system locations
if not _found:
    _search_paths = []
    
    if _system == 'Windows':
        # Windows common paths
        _search_paths.extend([
            os.environ.get('PROGRAMFILES', 'C:\\Program Files'),
            os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'),
            'C:\\Windows\\System32',
            'C:\\Windows\\SysWOW64',
        ])
    else:
        # Unix-like systems
        _search_paths.extend([
            '/usr/local/lib',
            '/usr/lib',
            '/opt/local/lib',
            '/opt/homebrew/lib',  # Homebrew on Apple Silicon
            '/usr/lib/x86_64-linux-gnu',  # Debian/Ubuntu 64-bit
            '/usr/lib/i386-linux-gnu',     # Debian/Ubuntu 32-bit
            '/usr/lib64',                   # RedHat/CentOS 64-bit
        ])
    
    # Add LD_LIBRARY_PATH entries
    if 'LD_LIBRARY_PATH' in os.environ:
        _search_paths.extend(os.environ['LD_LIBRARY_PATH'].split(':'))
    
    # Add DYLD_LIBRARY_PATH entries (macOS)
    if 'DYLD_LIBRARY_PATH' in os.environ:
        _search_paths.extend(os.environ['DYLD_LIBRARY_PATH'].split(':'))
    
    for path in _search_paths:
        if not exists(path):
            continue
            
        for lib_name in _standard_libs:
            lib_file = join(path, lib_name)
            if exists(lib_file):
                try:
                    _ks = cdll.LoadLibrary(lib_file)
                    _found = True
                    break
                except OSError:
                    pass
        
        if _found:
            break

# Final attempt: check Python's lib directory
if not _found:
    try:
        import distutils.sysconfig
        _python_lib = distutils.sysconfig.get_python_lib()
        for lib_name in _standard_libs:
            lib_file = join(_python_lib, 'keystone', lib_name)
            if exists(lib_file):
                try:
                    _ks = cdll.LoadLibrary(lib_file)
                    _found = True
                    break
                except OSError:
                    pass
    except ImportError:
        # distutils might not be available in some environments
        pass

if not _found:
    raise ImportError(
        "ERROR: fail to load the Keystone dynamic library. "
        "Please ensure Keystone is installed properly. "
        "Searched locations: module directory, system paths, "
        "LD_LIBRARY_PATH/DYLD_LIBRARY_PATH, and common system directories."
    )

__version__ = "%u.%u.%u" %(KS_VERSION_MAJOR, KS_VERSION_MINOR, KS_VERSION_EXTRA)

# setup all the function prototype
def _setup_prototype(lib, fname, restype, *argtypes):
    getattr(lib, fname).restype = restype
    getattr(lib, fname).argtypes = argtypes

kserr = c_int
ks_engine = c_void_p
ks_hook_h = c_size_t

_setup_prototype(_ks, "ks_version", c_uint, POINTER(c_int), POINTER(c_int))
_setup_prototype(_ks, "ks_arch_supported", c_bool, c_int)
_setup_prototype(_ks, "ks_open", kserr, c_uint, c_uint, POINTER(ks_engine))
_setup_prototype(_ks, "ks_close", kserr, ks_engine)
_setup_prototype(_ks, "ks_strerror", c_char_p, kserr)
_setup_prototype(_ks, "ks_errno", kserr, ks_engine)
_setup_prototype(_ks, "ks_option", kserr, ks_engine, c_int, c_void_p)
_setup_prototype(_ks, "ks_asm", c_int, ks_engine, c_char_p, c_uint64, POINTER(POINTER(c_ubyte)), POINTER(c_size_t), POINTER(c_size_t))
_setup_prototype(_ks, "ks_free", None, POINTER(c_ubyte))

# callback for OPT_SYM_RESOLVER option
KS_SYM_RESOLVER = CFUNCTYPE(c_bool, c_char_p, POINTER(c_uint64))

# access to error code via @errno of KsError
class KsError(Exception):
    def __init__(self, errno):
        self.errno = errno
        self.message = _ks.ks_strerror(self.errno)
        if not isinstance(self.message, str) and isinstance(self.message, bytes):
            self.message = self.message.decode('utf-8')
        super(KsError, self).__init__(self.message)

# return version binding
def ks_version():
    major = c_int()
    minor = c_int()
    combined = _ks.ks_version(byref(major), byref(minor))
    return (major.value, minor.value, combined)

# return the binding's version
def version_bind():
    return (KS_API_MAJOR, KS_API_MINOR, (KS_API_MAJOR << 8) + KS_API_MINOR)

# check to see if this engine supports a particular arch
def ks_arch_supported(query):
    return _ks.ks_arch_supported(query)

# print out debugging info
def debug():
    # is Keystone compiled in debug mode?
    if KS_MODE_LITTLE_ENDIAN & (1 << 31):
        print("Keystone was compiled in debug mode.")


class Ks(object):
    def __init__(self, arch, mode):
        # verify version compatibility with the core before doing anything
        (major, minor, _combined) = ks_version()
        if major != KS_API_MAJOR or minor != KS_API_MINOR:
            self._ksh = None
            # our binding version is different from the core's API version
            raise KsError(KS_ERR_VERSION)

        self._arch, self._mode = arch, mode
        self._ksh = c_void_p()
        status = _ks.ks_open(arch, mode, byref(self._ksh))
        if status != KS_ERR_OK:
            self._ksh = None
            raise KsError(status)
        # internal variables
        self._syntax = None

    def __del__(self):
        if self._ksh:
            try:
                status = _ks.ks_close(self._ksh)
                self._ksh = None
                if status != KS_ERR_OK:
                    raise KsError(status)
            except: # _ks might be pulled from under our feet
                pass

    # return the mode of this engine
    @property
    def mode(self):
        return self._mode

    # return the architecture of this engine
    @property
    def arch(self):
        return self._arch

    # return the syntax of this engine
    @property
    def syntax(self):
        return self._syntax

    # syntax setter: modify syntax of this engine
    @syntax.setter
    def syntax(self, style):
        status = _ks.ks_option(self._ksh, KS_OPT_SYNTAX, style)
        if status != KS_ERR_OK:
            raise KsError(status)
        # save syntax
        self._syntax = style

    @property
    def sym_resolver(self):
        return

    @sym_resolver.setter
    def sym_resolver(self, resolver):
        callback = KS_SYM_RESOLVER(resolver)
        status = _ks.ks_option(self._ksh, KS_OPT_SYM_RESOLVER, cast(callback, c_void_p))
        if status != KS_ERR_OK:
            raise KsError(status)

        # save resolver
        self._sym_resolver = callback

    def asm(self, string, addr=0, as_bytes=False):
        encode = POINTER(c_ubyte)()
        encode_size = c_size_t()
        stat_count = c_size_t()
        # encode to bytes by default
        if isinstance(string, str):
            string_bytes = string.encode('utf-8')
        else:
            string_bytes = string
        
        status = _ks.ks_asm(self._ksh, string_bytes, addr, byref(encode), byref(encode_size), byref(stat_count))
        if status != 0:
            raise KsError(status)
        else:
            if stat_count.value == 0:
                return (None, 0)
            else:
                if as_bytes:
                    encoding = string_at(encode, encode_size.value)
                else:
                    encoding = []
                    for i in range(encode_size.value):
                        encoding.append(encode[i])
                _ks.ks_free(encode)
                return (encoding, stat_count.value)


# print out debugging info
def debug():
    # is Keystone compiled in debug mode?
    if KS_MODE_LITTLE_ENDIAN & (1 << 31):
        print("Keystone was compiled in debug mode.")


# a dummy class to support cs_disasm_quick()
class _dummy:
    def __init__(self, data, size):
        self.bytes = data
        self.size = size


def asm(arch, mode, code, addr=0, as_bytes=False):
    # initialize encoder
    ks = Ks(arch, mode)

    return ks.asm(code, addr, as_bytes)