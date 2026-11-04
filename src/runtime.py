"""Source/frozen execution seam. Packaging never changes selected user settings."""
import os
from pathlib import Path
import sys


def initialize():
    if getattr(sys,'frozen',False):
        binary=Path(sys._MEIPASS)/'bin'
        os.environ['PATH']=str(binary)+os.pathsep+os.environ.get('PATH','')


def module_command(name,*arguments):
    if name not in ('commands','catalog'):raise ValueError('unsupported internal module')
    if getattr(sys,'frozen',False):return [str(Path(sys.executable).parent/'arranger-cli.exe'),'--module',name,*map(str,arguments)]
    return [sys.executable,'-B',str(Path(__file__).with_name(name+'.py')),*map(str,arguments)]


def native_tool(name):
    if name not in ('arranger-vst3.exe','arranger-playback.exe'):raise ValueError('unsupported bundled tool')
    if getattr(sys,'frozen',False):return Path(sys._MEIPASS)/'native'/name
    return Path(os.environ['LOCALAPPDATA'],'SampleArranger/tools/arranger-native')/name


def resource(name):
    if getattr(sys,'frozen',False):return Path(sys._MEIPASS)/'assets'/name
    return Path(__file__).resolve().parents[1]/'assets'/name
