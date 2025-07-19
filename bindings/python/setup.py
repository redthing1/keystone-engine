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
import tempfile
from pathlib import Path
from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
from setuptools.command.bdist_wheel import bdist_wheel
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
    LIBRARY_FILE = 'libkeystone.dylib'
    LIBRARY_PATTERNS = ['libkeystone*.dylib']
elif SYSTEM == 'Windows':
    LIBRARY_FILE = 'keystone.dll'
    LIBRARY_PATTERNS = ['keystone.dll']
else:
    LIBRARY_FILE = 'libkeystone.so'
    LIBRARY_PATTERNS = ['libkeystone.so*']


def check_cmake():
    """Ensure CMake is available"""
    try:
        subprocess.run(['cmake', '--version'], 
                     capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise DistutilsSetupError(
            "CMake is required to build Keystone. "
            "Install it from https://cmake.org/download/"
        )


def build_keystone_library(build_temp_dir):
    """Build Keystone library using CMake"""
    check_cmake()
    
    # Use temp directory for build
    cmake_build_dir = Path(build_temp_dir) / 'keystone_cmake_build'
    cmake_build_dir.mkdir(parents=True, exist_ok=True)
    
    # CMake configuration
    cmake_args = [
        f'-DCMAKE_BUILD_TYPE=Release',
        '-DBUILD_SHARED_LIBS=ON',
        '-DBUILD_LIBS_ONLY=ON',
        '-DCMAKE_POLICY_VERSION_MINIMUM=3.5',
    ]
    
    # Platform-specific settings
    if SYSTEM != 'Windows' and shutil.which('ninja'):
        cmake_args.extend(['-G', 'Ninja'])
    
    # Configure
    print(f"Configuring Keystone in {cmake_build_dir}")
    try:
        subprocess.run(
            ['cmake', str(PROJECT_ROOT)] + cmake_args,
            cwd=cmake_build_dir,
            check=True
        )
    except subprocess.CalledProcessError as e:
        raise DistutilsSetupError(f"CMake configuration failed: {e}")
    
    # Build
    print("Building Keystone library (this may take a few minutes)...")
    build_cmd = ['cmake', '--build', '.', '--config', 'Release']
    
    # Parallel build on Unix-like systems
    if SYSTEM != 'Windows':
        import multiprocessing
        build_cmd.extend(['--', f'-j{multiprocessing.cpu_count()}'])
    
    try:
        subprocess.run(build_cmd, cwd=cmake_build_dir, check=True)
    except subprocess.CalledProcessError as e:
        raise DistutilsSetupError(f"Build failed: {e}")
    
    # Find the built library
    search_dirs = [
        cmake_build_dir / 'llvm' / 'lib',
        cmake_build_dir / 'llvm' / 'bin',
        cmake_build_dir / 'lib',
        cmake_build_dir / 'bin',
    ]
    
    if SYSTEM == 'Linux' and IS_64BITS:
        search_dirs.insert(1, cmake_build_dir / 'llvm' / 'lib64')
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        
        for pattern in LIBRARY_PATTERNS:
            for lib_file in search_dir.glob(pattern):
                if lib_file.is_file():
                    return lib_file, search_dir
    
    raise DistutilsSetupError(
        f"Could not find built library. Searched in: {search_dirs}"
    )


class CustomBuildExt(build_ext):
    """Custom build_ext that builds Keystone library first"""
    
    def run(self):
        # Check if library already exists
        lib_exists = False
        for pattern in LIBRARY_PATTERNS:
            if list(KEYSTONE_DIR.glob(pattern)):
                lib_exists = True
                break
        
        if not lib_exists:
            # Build the library
            print("Building Keystone library from source...")
            lib_file, lib_dir = build_keystone_library(self.build_temp)
            
            # Ensure keystone directory exists
            KEYSTONE_DIR.mkdir(parents=True, exist_ok=True)
            
            # Copy the library and related files
            shutil.copy2(lib_file, KEYSTONE_DIR / lib_file.name)
            print(f"Copied library: {lib_file.name}")
            
            # On Unix, handle versioned libraries and symlinks
            if SYSTEM != 'Windows':
                for related in lib_dir.glob('libkeystone*'):
                    if related.name.startswith('libkeystone'):
                        dest_file = KEYSTONE_DIR / related.name
                        if related.is_symlink():
                            # Recreate symlink
                            target = os.readlink(related)
                            dest_file.unlink(missing_ok=True)
                            dest_file.symlink_to(target)
                        elif related.is_file() and related != lib_file:
                            shutil.copy2(related, dest_file)
            
            # Fix library paths on macOS
            if SYSTEM == 'Darwin':
                self.fix_macos_rpath(KEYSTONE_DIR / lib_file.name)
        else:
            print("Using existing Keystone library")
        
        # Build extensions
        super().run()
    
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
            pass


class CustomBdistWheel(bdist_wheel):
    """Custom bdist_wheel to ensure library is included"""
    
    def run(self):
        # First ensure library is built
        self.run_command('build_ext')
        # Then build the wheel
        super().run()


# Create _dummy.c if it doesn't exist
dummy_c = ROOT_DIR / '_dummy.c'
if not dummy_c.exists():
    dummy_c.write_text('// Dummy C file for triggering build_ext\nvoid dummy(void) {}\n')

# Read README for long description
long_description = ''
readme_file = ROOT_DIR / 'README.md'
if readme_file.exists():
    long_description = readme_file.read_text(encoding='utf-8')

setup(
    name='keystone-engine',
    version=VERSION,
    author='Nguyen Anh Quynh',
    author_email='aquynh@gmail.com',
    description='Keystone assembler engine',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://www.keystone-engine.org',
    license='GPL-2.0',
    
    packages=['keystone'],
    package_data={
        'keystone': [
            '*.py',
            '*.so', '*.so.*',  # Linux
            '*.dylib',         # macOS  
            '*.dll',           # Windows
            'lib*',            # versioned libraries
        ],
    },
    include_package_data=True,
    
    # Dummy extension to trigger build_ext
    ext_modules=[Extension('_keystone_dummy', sources=['_dummy.c'])],
    
    cmdclass={
        'build_ext': CustomBuildExt,
        'bdist_wheel': CustomBdistWheel,
    },
    
    python_requires='>=3.6',
    
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Assemblers',
        'Topic :: Security',
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
    ],
    
    zip_safe=False,
)