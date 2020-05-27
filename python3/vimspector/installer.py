#!/usr/bin/env python3

# vimspector - A multi-language debugging system for Vim
# Copyright 2019 Ben Jackson
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from urllib import request
import contextlib
import functools
import gzip
import hashlib
import io
import os
import shutil
import ssl
import string
import subprocess
import sys
import tarfile
import time
import traceback
import zipfile
import json

from vimspector import install


class Options:
  vimspector_base = None
  no_check_certificate = False


options = Options()


def Configure( **kwargs ):
  for k, v in kwargs.items():
    setattr( options, k, v )


GADGETS = {
  'vscode-cpptools': {
    'language': 'c',
    'download': {
      'url': 'https://github.com/Microsoft/vscode-cpptools/releases/download/'
             '${version}/${file_name}',
    },
    'do': lambda name, root, gadget: InstallCppTools( name, root, gadget ),
    'all': {
      'version': '0.27.0',
    },
    'linux': {
      'file_name': 'cpptools-linux.vsix',
      'checksum':
        '3695202e1e75a03de18049323b66d868165123f26151f8c974a480eaf0205435'
    },
    'macos': {
      'file_name': 'cpptools-osx.vsix',
      'checksum':
        'cb061e3acd7559a539e5586f8d3f535101c4ec4e8a48195856d1d39380b5cf3c',
    },
    'windows': {
      'file_name': 'cpptools-win32.vsix',
      'checksum': None,
    },
    "adapters": {
      "vscode-cpptools": {
        "name": "cppdbg",
        "command": [
          "${gadgetDir}/vscode-cpptools/debugAdapters/OpenDebugAD7"
        ],
        "attach": {
          "pidProperty": "processId",
          "pidSelect": "ask"
        },
        "configuration": {
          "type": "cppdbg",
          "args": [],
          "cwd": "${workspaceRoot}",
          "environment": [],
        }
      },
    },
  },
  'vscode-python': {
    'language': 'python.legacy',
    'enabled': False,
    'download': {
      'url': 'https://github.com/Microsoft/vscode-python/releases/download/'
             '${version}/${file_name}',
    },
    'all': {
      'version': '2019.11.50794',
      'file_name': 'ms-python-release.vsix',
      'checksum':
        '6a9edf9ecabed14aac424e6007858068204a3638bf3bb4f235bd6035d823acc6',
    },
    'adapters': {
      "vscode-python": {
        "name": "vscode-python",
        "command": [
          "node",
          "${gadgetDir}/vscode-python/out/client/debugger/debugAdapter/main.js",
        ],
      }
    },
  },
  'debugpy': {
    'language': 'python',
    'download': {
      'url': 'https://github.com/microsoft/debugpy/archive/${file_name}'
    },
    'all': {
      'version': '1.0.0b8',
      'file_name': 'v1.0.0b8.zip',
      'checksum':
        '07c208bcd2a18088757f3bcb6f3bfc68d42c16a504c716e35d34fbe6b010a7b3'
    },
    'do': lambda name, root, gadget: InstallDebugpy( name, root, gadget ),
    'adapters': {
      'debugpy': {
        "command": [
          sys.executable,
          "${gadgetDir}/debugpy/build/lib/debugpy/adapter"
        ],
        "name": "debugpy",
        "configuration": {
          "python": sys.executable,
          # Don't debug into subprocesses, as this leads to problems (vimspector
          # doesn't support the custom messages)
          # https://github.com/puremourning/vimspector/issues/141
          "subProcess": False,
        }
      }
    },
  },
  'vscode-java-debug': {
    'language': 'java',
    'enabled': False,
    'download': {
      'url': 'https://github.com/microsoft/vscode-java-debug/releases/download/'
             '${version}/${file_name}',
    },
    'all': {
      'version': '0.26.0',
      'file_name': 'vscjava.vscode-java-debug-0.26.0.vsix',
      'checksum':
        'de49116ff3a3c941dad0c36d9af59baa62cd931e808a2ab392056cbb235ad5ef',
    },
    'adapters': {
      "vscode-java": {
        "name": "vscode-java",
        "port": "${DAPPort}",
      }
    },
  },
  'java-language-server': {
    'language': 'javac',
    'enabled': False,
    'download': {
      'url': 'https://marketplace.visualstudio.com/_apis/public/gallery/'
             'publishers/georgewfraser/vsextensions/vscode-javac/${version}/'
             'vspackage',
      'target': 'georgewfraser.vscode-javac-0.2.31.vsix.gz',
      'format': 'zip.gz',
    },
    'all': {
      'version': '0.2.31',
      'file_name': 'georgewfraser.vscode-javac-0.2.31.vsix.gz',
      'checksum':
        '5b0248ec1198d3ece9a9c6b9433b30c22e308f0ae6e4c7bd09cd943c454e3e1d',
    },
    'adapters': {
      "vscode-javac": {
        "name": "vscode-javac",
        "type": "vscode-javac",
        "command": [
          "${gadgetDir}/java-language-server/dist/debug_adapter_mac.sh"
        ],
        "attach": {
          "pidSelect": "none"
        }
      }
    },
  },
  'tclpro': {
    'language': 'tcl',
    'repo': {
      'url': 'https://github.com/puremourning/TclProDebug',
      'ref': 'f5c56b7067661ce84e205765060224076569ae0e', # master 26/10/2019
    },
    'do': lambda name, root, gadget: InstallTclProDebug( name, root, gadget )
  },
  'netcoredbg': {
    'language': 'csharp',
    'enabled': False,
    'download': {
      'url': 'https://github.com/Samsung/netcoredbg/releases/download/latest/'
             '${file_name}',
      'format': 'tar',
    },
    'all': {
      'version': 'master'
    },
    'macos': {
      'file_name': 'netcoredbg-osx-master.tar.gz',
      'checksum':
        'c1dc6ed58c3f5b0473cfb4985a96552999360ceb9795e42d9c9be64af054f821',
    },
    'linux': {
      'file_name': 'netcoredbg-linux-master.tar.gz',
      'checksum': '',
    },
    'do': lambda name, root, gadget: MakeSymlink(
      install.GetGadgetDir( options.vimspector_base ),
      name,
      os.path.join( root, 'netcoredbg' ) ),
    'adapters': {
      'netcoredbg': {
        "name": "netcoredbg",
        "command": [
          "${gadgetDir}/netcoredbg/netcoredbg",
          "--interpreter=vscode"
        ],
        "attach": {
          "pidProperty": "processId",
          "pidSelect": "ask"
        },
      },
    }
  },
  'vscode-mono-debug': {
    'language': 'csharp',
    'enabled': False,
    'download': {
      'url': 'https://marketplace.visualstudio.com/_apis/public/gallery/'
             'publishers/ms-vscode/vsextensions/mono-debug/${version}/'
             'vspackage',
      'target': 'vscode-mono-debug.vsix.gz',
      'format': 'zip.gz',
    },
    'all': {
      'file_name': 'vscode-mono-debug.vsix',
      'version': '0.15.8',
      'checksum':
          '723eb2b621b99d65a24f215cb64b45f5fe694105613a900a03c859a62a810470',
    },
    'adapters': {
      'vscode-mono-debug': {
        "name": "mono-debug",
        "command": [
          "mono",
          "${gadgetDir}/vscode-mono-debug/bin/Release/mono-debug.exe"
        ],
        "attach": {
          "pidSelect": "none"
        },
      },
    }
  },
  'vscode-bash-debug': {
    'language': 'bash',
    'download': {
      'url': 'https://github.com/rogalmic/vscode-bash-debug/releases/'
             'download/${version}/${file_name}',
    },
    'all': {
      'file_name': 'bash-debug-0.3.7.vsix',
      'version': 'v0.3.7',
      'checksum':
        '7b73e5b4604375df8658fb5a72c645c355785a289aa785a986e508342c014bb4',
    },
    'do': lambda name, root, gadget: InstallBashDebug( name, root, gadget ),
    'adapters': {
      "vscode-bash": {
        "name": "bashdb",
        "command": [
          "node",
          "${gadgetDir}/vscode-bash-debug/out/bashDebug.js"
        ],
        "variables": {
          "BASHDB_HOME": "${gadgetDir}/vscode-bash-debug/bashdb_dir"
        },
        "configuration": {
          "request": "launch",
          "type": "bashdb",
          "program": "${file}",
          "args": [],
          "env": {},
          "pathBash": "bash",
          "pathBashdb": "${BASHDB_HOME}/bashdb",
          "pathBashdbLib": "${BASHDB_HOME}",
          "pathCat": "cat",
          "pathMkfifo": "mkfifo",
          "pathPkill": "pkill",
          "cwd": "${workspaceRoot}",
          "terminalKind": "integrated",
        }
      }
    }
  },
  'vscode-go': {
    'language': 'go',
    'download': {
      'url': 'https://github.com/microsoft/vscode-go/releases/download/'
             '${version}/${file_name}'
    },
    'all': {
      'version': '0.11.4',
      'file_name': 'Go-0.11.4.vsix',
      'checksum':
        'ff7d7b944da5448974cb3a0086f4a2fd48e2086742d9c013d6964283d416027e'
    },
    'adapters': {
      'vscode-go': {
        'name': 'delve',
        'command': [
          'node',
          '${gadgetDir}/vscode-go/out/src/debugAdapter/goDebug.js'
        ],
      },
    },
  },
  'vscode-php-debug': {
    'language': 'php',
    'enabled': False,
    'download': {
      'url':
        'https://github.com/felixfbecker/vscode-php-debug/releases/download/'
        '${version}/${file_name}',
    },
    'all': {
      'version': 'v1.13.0',
      'file_name': 'php-debug.vsix',
      'checksum':
        '8a51e593458fd14623c1c89ebab87347b087d67087717f18bcf77bb788052718',
    },
    'adapters': {
      'vscode-php-debug': {
        'name': "php-debug",
        'command': [
          'node',
          "${gadgetDir}/vscode-php-debug/out/phpDebug.js",
        ]
      }
    }
  },
  'vscode-node-debug2': {
    'language': 'node',
    'enabled': False,
    'repo': {
      'url': 'https://github.com/microsoft/vscode-node-debug2',
      'ref': 'v1.42.0',
    },
    'do': lambda name, root, gadget: InstallNodeDebug( name, root, gadget ),
    'adapters': {
      'vscode-node': {
        'name': 'node2',
        'type': 'node2',
        'command': [
          'node',
          '${gadgetDir}/vscode-node-debug2/out/src/nodeDebug.js'
        ]
      },
    },
  },
  'debugger-for-chrome': {
    'language': 'chrome',
    'enabled': False,
    'download': {
      'url': 'https://marketplace.visualstudio.com/_apis/public/gallery/'
             'publishers/msjsdiag/vsextensions/'
             'debugger-for-chrome/${version}/vspackage',
      'target': 'msjsdiag.debugger-for-chrome-4.12.0.vsix.gz',
      'format': 'zip.gz',
    },
    'all': {
      'version': '4.12.0',
      'file_name': 'msjsdiag.debugger-for-chrome-4.12.0.vsix',
      'checksum':
        '0df2fe96d059a002ebb0936b0003e6569e5a5c35260dc3791e1657d27d82ccf5'
    },
    'adapters': {
      'chrome': {
        'name': 'debugger-for-chrome',
        'type': 'chrome',
        'command': [
          'node',
          '${gadgetDir}/debugger-for-chrome/out/src/chromeDebug.js'
        ],
      },
    },
  },
}


def InstallCppTools( name, root, gadget ):
  extension = os.path.join( root, 'extension' )

  # It's hilarious, but the execute bits aren't set in the vsix. So they
  # actually have javascript code which does this. It's just a horrible horrible
  # hack that really is not funny.
  MakeExecutable( os.path.join( extension, 'debugAdapters', 'OpenDebugAD7' ) )
  with open( os.path.join( extension, 'package.json' ) ) as f:
    package = json.load( f )
    runtime_dependencies = package[ 'runtimeDependencies' ]
    for dependency in runtime_dependencies:
      for binary in dependency.get( 'binaries' ):
        file_path = os.path.abspath( os.path.join( extension, binary ) )
        if os.path.exists( file_path ):
          MakeExecutable( os.path.join( extension, binary ) )

  MakeExtensionSymlink( name, root )


def InstallBashDebug( name, root, gadget ):
  MakeExecutable( os.path.join( root, 'extension', 'bashdb_dir', 'bashdb' ) )
  MakeExtensionSymlink( name, root )


def InstallDebugpy( name, root, gadget ):
  wd = os.getcwd()
  root = os.path.join( root, 'debugpy-{}'.format( gadget[ 'version' ] ) )
  os.chdir( root )
  try:
    subprocess.check_call( [ sys.executable, 'setup.py', 'build' ] )
  finally:
    os.chdir( wd )

  MakeSymlink( install.GetGadgetDir( options.vimspector_base ),
               name,
               root )


def InstallTclProDebug( name, root, gadget ):
  configure = [ './configure' ]

  if install.GetOS() == 'macos':
    # Apple removed the headers from system frameworks because they are
    # determined to make life difficult. And the TCL configure scripts are super
    # old so don't know about this. So we do their job for them and try and find
    # a tclConfig.sh.
    #
    # NOTE however that in Apple's infinite wisdom, installing the "headers" in
    # the other location is actually broken because the paths in the
    # tclConfig.sh are pointing at the _old_ location. You actually do have to
    # run the package installation which puts the headers back in order to work.
    # This is why the below list is does not contain stuff from
    # /Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform
    #  '/Applications/Xcode.app/Contents/Developer/Platforms'
    #    '/MacOSX.platform/Developer/SDKs/MacOSX.sdk/System'
    #    '/Library/Frameworks/Tcl.framework',
    #  '/Applications/Xcode.app/Contents/Developer/Platforms'
    #    '/MacOSX.platform/Developer/SDKs/MacOSX.sdk/System'
    #    '/Library/Frameworks/Tcl.framework/Versions'
    #    '/Current',
    for p in [ '/usr/local/opt/tcl-tk/lib' ]:
      if os.path.exists( os.path.join( p, 'tclConfig.sh' ) ):
        configure.append( '--with-tcl=' + p )
        break


  with CurrentWorkingDir( os.path.join( root, 'lib', 'tclparser' ) ):
    subprocess.check_call( configure )
    subprocess.check_call( [ 'make' ] )

  MakeSymlink( install.GetGadgetDir( options.vimspector_base ),
               name,
               root )


def InstallNodeDebug( name, root, gadget ):
  node_version = subprocess.check_output( [ 'node', '--version' ],
                                          universal_newlines=True ).strip()
  print( "Node.js version: {}".format( node_version ) )
  if list( map( int, node_version[ 1: ].split( '.' ) ) ) >= [ 12, 0, 0 ]:
    print( "Can't install vscode-debug-node2:" )
    print( "Sorry, you appear to be running node 12 or later. That's not "
           "compatible with the build system for this extension, and as far as "
           "we know, there isn't a pre-built independent package." )
    print( "My advice is to install nvm, then do:" )
    print( "  $ nvm install --lts 10" )
    print( "  $ nvm use --lts 10" )
    print( "  $ ./install_gadget.py --enable-node ..." )
    raise RuntimeError( 'Invalid node environent for node debugger' )

  with CurrentWorkingDir( root ):
    subprocess.check_call( [ 'npm', 'install' ] )
    subprocess.check_call( [ 'npm', 'run', 'build' ] )
  MakeSymlink( install.GetGadgetDir( options.vimspector_base ),
               name,
               root )


def InstallGagdet( name, gadget, failed, all_adapters ):
  try:
    v = {}
    v.update( gadget.get( 'all', {} ) )
    v.update( gadget.get( install.GetOS(), {} ) )

    if 'download' in gadget:
      if 'file_name' not in v:
        raise RuntimeError( "Unsupported OS {} for gadget {}".format(
          install.GetOS(),
          name ) )

      destination = os.path.join(
        install.GetGadgetDir( options.vimspector_base ),
        'download',
        name,
        v[ 'version' ] )

      url = string.Template( gadget[ 'download' ][ 'url' ] ).substitute( v )

      file_path = DownloadFileTo(
        url,
        destination,
        file_name = gadget[ 'download' ].get( 'target' ),
        checksum = v.get( 'checksum' ),
        check_certificate = not options.no_check_certificate )

      root = os.path.join( destination, 'root' )
      ExtractZipTo( file_path,
                    root,
                    format = gadget[ 'download' ].get( 'format', 'zip' ) )
    elif 'repo' in gadget:
      url = string.Template( gadget[ 'repo' ][ 'url' ] ).substitute( v )
      ref = string.Template( gadget[ 'repo' ][ 'ref' ] ).substitute( v )

      destination = os.path.join(
        install.GetGadgetDir( options.vimspector_base ),
        'download',
        name )
      CloneRepoTo( url, ref, destination )
      root = destination

    if 'do' in gadget:
      gadget[ 'do' ]( name, root, v )
    else:
      MakeExtensionSymlink( name, root )

    all_adapters.update( gadget.get( 'adapters', {} ) )

    print( "Done installing {}".format( name ) )
  except Exception as e:
    traceback.print_exc()
    failed.append( name )
    print( "FAILED installing {}: {}".format( name, e ) )


def ReadAdapters( read_existing = True ):
  if read_existing:
    with open( install.GetGadgetConfigFile( options.vimspector_base ),
               'r' ) as f:
      all_adapters = json.load( f ).get( 'adapters', {} )
  else:
    all_adapters = {}

  # Include "built-in" adapter for multi-session mode
  all_adapters.update( {
    'multi-session': {
      'port': '${port}',
      'host': '${host}'
    },
  } )

  return all_adapters


def WriteAdapters( all_adapters, to_file=None ):
  adapter_config = json.dumps ( { 'adapters': all_adapters },
                                indent=2,
                                sort_keys=True )

  if to_file:
    to_file.write( adapter_config )
  else:
    with open( install.GetGadgetConfigFile( options.vimspector_base ),
               'w' ) as f:
      f.write( adapter_config )



@contextlib.contextmanager
def CurrentWorkingDir( d ):
  cur_d = os.getcwd()
  try:
    os.chdir( d )
    yield
  finally:
    os.chdir( cur_d )


def MakeExecutable( file_path ):
  # TODO: import stat and use them by _just_ adding the X bit.
  print( 'Making executable: {}'.format( file_path ) )
  os.chmod( file_path, 0o755 )



def WithRetry( f ):
  retries = 5
  timeout = 1 # seconds

  @functools.wraps( f )
  def wrapper( *args, **kwargs ):
    thrown = None
    for _ in range( retries ):
      try:
        return f( *args, **kwargs )
      except Exception as e:
        thrown = e
        print( "Failed - {}, will retry in {} seconds".format( e, timeout ) )
        time.sleep( timeout )
    raise thrown

  return wrapper


@WithRetry
def UrlOpen( *args, **kwargs ):
  return request.urlopen( *args, **kwargs )


def DownloadFileTo( url,
                    destination,
                    file_name = None,
                    checksum = None,
                    check_certificate = True ):
  if not file_name:
    file_name = url.split( '/' )[ -1 ]

  file_path = os.path.abspath( os.path.join( destination, file_name ) )

  if not os.path.isdir( destination ):
    os.makedirs( destination )

  if os.path.exists( file_path ):
    if checksum:
      if ValidateCheckSumSHA256( file_path, checksum ):
        print( "Checksum matches for {}, using it".format( file_path ) )
        return file_path
      else:
        print( "Checksum doesn't match for {}, removing it".format(
          file_path ) )

    print( "Removing existing {}".format( file_path ) )
    os.remove( file_path )

  r = request.Request( url, headers = { 'User-Agent': 'Vimspector' } )

  print( "Downloading {} to {}/{}".format( url, destination, file_name ) )

  if not check_certificate:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    kwargs = { "context":  context }
  else:
    kwargs = {}

  with contextlib.closing( UrlOpen( r, **kwargs ) ) as u:
    with open( file_path, 'wb' ) as f:
      f.write( u.read() )

  if checksum:
    if not ValidateCheckSumSHA256( file_path, checksum ):
      raise RuntimeError(
        'Checksum for {} ({}) does not match expected {}'.format(
          file_path,
          GetChecksumSHA254( file_path ),
          checksum ) )
  else:
    print( "Checksum for {}: {}".format( file_path,
                                         GetChecksumSHA254( file_path ) ) )

  return file_path


def GetChecksumSHA254( file_path ):
  with open( file_path, 'rb' ) as existing_file:
    return hashlib.sha256( existing_file.read() ).hexdigest()


def ValidateCheckSumSHA256( file_path, checksum ):
  existing_sha256 = GetChecksumSHA254( file_path )
  return existing_sha256 == checksum


def RemoveIfExists( destination ):
  if os.path.islink( destination ):
    print( "Removing file {}".format( destination ) )
    os.remove( destination )
    return

  N = 1


  def BackupDir():
    return "{}.{}".format( destination, N )

  while os.path.isdir( BackupDir() ):
    print( "Removing old dir {}".format( BackupDir() ) )
    try:
      shutil.rmtree( BackupDir() )
      print ( "OK, removed it" )
      break
    except OSError:
      print ( "FAILED" )
      N = N + 1

  if os.path.exists( destination ):
    print( "Removing dir {}".format( destination ) )
    try:
      shutil.rmtree( destination )
    except OSError:
      print( "FAILED, moving {} to dir {}".format( destination, BackupDir() ) )
      os.rename( destination, BackupDir() )


# Python's ZipFile module strips execute bits from files, for no good reason
# other than crappy code. Let's do it's job for it.
class ModePreservingZipFile( zipfile.ZipFile ):
  def extract( self, member, path = None, pwd = None ):
    if not isinstance( member, zipfile.ZipInfo ):
      member = self.getinfo( member )

    if path is None:
      path = os.getcwd()

    ret_val = self._extract_member( member, path, pwd )
    attr = member.external_attr >> 16
    os.chmod( ret_val, attr )
    return ret_val


def ExtractZipTo( file_path, destination, format ):
  print( "Extracting {} to {}".format( file_path, destination ) )
  RemoveIfExists( destination )

  if format == 'zip':
    with ModePreservingZipFile( file_path ) as f:
      f.extractall( path = destination )
  elif format == 'zip.gz':
    with gzip.open( file_path, 'rb' ) as f:
      file_contents = f.read()

    with ModePreservingZipFile( io.BytesIO( file_contents ) ) as f:
      f.extractall( path = destination )

  elif format == 'tar':
    try:
      with tarfile.open( file_path ) as f:
        f.extractall( path = destination )
    except Exception:
      # There seems to a bug in python's tarfile that means it can't read some
      # windows-generated tar files
      os.makedirs( destination )
      with CurrentWorkingDir( destination ):
        subprocess.check_call( [ 'tar', 'zxvf', file_path ] )


def MakeExtensionSymlink( name, root ):
  MakeSymlink( install.GetGadgetDir( options.vimspector_base ),
               name,
               os.path.join( root, 'extension' ) ),


def MakeSymlink( in_folder, link, pointing_to ):
  RemoveIfExists( os.path.join( in_folder, link ) )

  in_folder = os.path.abspath( in_folder )
  pointing_to_relative = os.path.relpath( os.path.abspath( pointing_to ),
                                          in_folder )
  link_path = os.path.join( in_folder, link )

  if install.GetOS() == 'windows':
    # While symlinks do exist on Windows, they require elevated privileges, so
    # let's use a directory junction which is all we need.
    link_path = os.path.abspath( link_path )
    if os.path.isdir( link_path ):
      os.rmdir( link_path )
    subprocess.check_call( [ 'cmd.exe',
                             '/c',
                             'mklink',
                             '/J',
                             link_path,
                             pointing_to ] )
  else:
    os.symlink( pointing_to_relative, link_path )


def CloneRepoTo( url, ref, destination ):
  RemoveIfExists( destination )
  git_in_repo = [ 'git', '-C', destination ]
  subprocess.check_call( [ 'git', 'clone', url, destination ] )
  subprocess.check_call( git_in_repo + [ 'checkout', ref ] )
  subprocess.check_call( git_in_repo + [ 'submodule', 'sync', '--recursive' ] )
  subprocess.check_call( git_in_repo + [ 'submodule',
                                         'update',
                                         '--init',
                                         '--recursive' ] )


def AbortIfSUperUser( force_sudo ):
  # TODO: We should probably check the effective uid too
  is_su = False
  if 'SUDO_COMMAND' in os.environ:
    is_su = True

  if is_su:
    if force_sudo:
      print( "*** RUNNING AS SUPER USER DUE TO force_sudo! "
             "    All bets are off. ***" )
    else:
      sys.exit( "This script should *not* be run as super user. Aborting." )
