#!/usr/bin/env python
"""
Keystone Engine Python bindings
Builds the native library from source during installation
"""
import os
import sys
import platform
import subprocess
import shutil
from pathlib import Path
from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
from distutils.errors import DistutilsSetupError

VERSION = '0.9.3'

# Paths
ROOT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = ROOT_DIR.parent.parent
KEYSTONE_DIR = ROOT_DIR / 'keystone'

# Platform detection
SYSTEM = platform.system()
IS_64BITS = sys.maxsize > 2**32

# Library names per platform
if SYSTEM == 'Darwin':
    LIBRARY_PATTERNS = ['libkeystone*.dylib']
elif SYSTEM == 'Windows':
    LIBRARY_PATTERNS = ['keystone.dll']
else:
    LIBRARY_PATTERNS = ['libkeystone.so*']


class CMakeBuildExt(build_ext):
    """Build extension that compiles Keystone library from source"""
    
    def run(self):
        self.check_cmake()
        self.build_library()
        super().run()
    
    def check_cmake(self):
        """Ensure CMake is available"""
        try:
            subprocess.run(['cmake', '--version'], 
                         capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            raise DistutilsSetupError(
                "CMake is required to build Keystone. "
                "Install it from https://cmake.org/download/"
            )
    
    def build_library(self):
        """Build Keystone library using CMake"""
        # Use a subdirectory of build_temp for CMake
        build_dir = Path(self.build_temp) / 'keystone_cmake'
        build_dir.mkdir(parents=True, exist_ok=True)
        
        # Basic CMake configuration
        cmake_args = [
            '-DCMAKE_BUILD_TYPE=Release',
            '-DBUILD_SHARED_LIBS=ON',
            '-DBUILD_LIBS_ONLY=ON',
        ]
        
        # Platform-specific generator
        if SYSTEM == 'Windows':
            # Let CMake auto-detect the best generator
            pass
        elif shutil.which('ninja'):
            cmake_args.extend(['-G', 'Ninja'])
        
        # Configure
        print(f"Configuring Keystone in {build_dir}")
        subprocess.run(
            ['cmake', str(PROJECT_ROOT)] + cmake_args,
            cwd=build_dir,
            check=True
        )
        
        # Build
        print("Building Keystone (this may take a few minutes)...")
        build_cmd = ['cmake', '--build', '.', '--config', 'Release']
        
        # Parallel build
        if SYSTEM != 'Windows':
            import multiprocessing
            build_cmd.extend(['--', f'-j{multiprocessing.cpu_count()}'])
        
        subprocess.run(build_cmd, cwd=build_dir, check=True)
        
        # Copy library to package
        self.copy_library(build_dir)
    
    def copy_library(self, build_dir):
        """Find and copy the built library"""
        # Search paths
        lib_dirs = [
            build_dir / 'llvm' / 'lib',
            build_dir / 'llvm' / 'bin',
            build_dir / 'lib',
            build_dir / 'bin',
        ]
        
        if SYSTEM == 'Linux' and IS_64BITS:
            lib_dirs.insert(1, build_dir / 'llvm' / 'lib64')
        
        # Find the library
        found = False
        for lib_dir in lib_dirs:
            if not lib_dir.exists():
                continue
            
            for pattern in LIBRARY_PATTERNS:
                for lib_file in lib_dir.glob(pattern):
                    if lib_file.is_file():
                        # Ensure destination exists
                        KEYSTONE_DIR.mkdir(exist_ok=True)
                        
                        # Copy library
                        dest = KEYSTONE_DIR / lib_file.name
                        shutil.copy2(lib_file, dest)
                        print(f"Installed library: {dest.name}")
                        found = True
                        
                        # Copy related files (symlinks, etc)
                        if SYSTEM != 'Windows':
                            for related in lib_dir.glob('libkeystone*'):
                                dest_file = KEYSTONE_DIR / related.name
                                if related.is_symlink():
                                    target = os.readlink(related)
                                    dest_file.unlink(missing_ok=True)
                                    dest_file.symlink_to(target)
                                elif related.is_file():
                                    shutil.copy2(related, dest_file)
                        
                        # Fix macOS library paths
                        if SYSTEM == 'Darwin':
                            self.fix_macos_rpath(dest)
                        
                        break
                
                if found:
                    break
            
            if found:
                break
        
        if not found:
            raise DistutilsSetupError(
                f"Could not find built library in {build_dir}"
            )
    
    def fix_macos_rpath(self, lib_path):
        """Make macOS library relocatable"""
        if not shutil.which('install_name_tool'):
            return
        
        try:
            # Set library ID to @loader_path relative
            subprocess.run([
                'install_name_tool',
                '-id', f'@loader_path/{lib_path.name}',
                str(lib_path)
            ], capture_output=True, check=True)
        except subprocess.CalledProcessError:
            # Non-fatal
            pass


setup(
    name='keystone-engine',
    version=VERSION,
    author='Nguyen Anh Quynh',
    author_email='aquynh@gmail.com',
    description='Keystone assembler engine',
    long_description=open('README.md').read() if os.path.exists('README.md') else '',
    long_description_content_type='text/markdown',
    url='https://www.keystone-engine.org',
    license='GPL-2.0',
    
    packages=['keystone'],
    package_data={
        'keystone': ['*.py', '*.so*', '*.dylib', '*.dll', 'lib*'],
    },
    
    # Minimal dummy extension to trigger build
    ext_modules=[Extension('_keystone_dummy', sources=['_dummy.c'])],
    cmdclass={'build_ext': CMakeBuildExt},
    
    python_requires='>=3.6',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Assemblers',
        'Topic :: Security',
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        'Programming Language :: Python :: 3',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
    ],
    
    zip_safe=False,
)