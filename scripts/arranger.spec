# Private Windows onedir package. Build-time paths come from package.ps1, not user data.
import os
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

root=Path(os.environ['ARRANGER_SOURCE_ROOT'])
native=Path(os.environ['ARRANGER_NATIVE_BUILD'])
assets=Path(os.environ['ARRANGER_PACKAGE_ASSETS'])
icon=str(assets/'arranger.ico')
data=[(str(assets/'arranger.png'),'assets'),(str(root/'LICENSE'),'licenses'),
      (str(root/'docs/THIRD_PARTY.md'),'licenses'),(str(root/'docs/CLI_AND_BROKER.md'),'docs')]
for name in ('arranger-vst3.exe','arranger-playback.exe'):data.append((str(native/name),'native'))
for variable in ('ARRANGER_FFMPEG','ARRANGER_FFPROBE','ARRANGER_FFPLAY'):data.append((os.environ[variable],'bin'))
for package in ('PySide6-Essentials','shiboken6','numpy'):data+=copy_metadata(package)

cli=Analysis([str(root/'src/launch_cli.py')],pathex=[str(root/'src')],datas=data,excludes=['tkinter','workspace','PySide6'],noarchive=False)
gui=Analysis([str(root/'src/launch_workspace.py')],pathex=[str(root/'src')],datas=data,excludes=['tkinter'],noarchive=False)
cli_exe=EXE(PYZ(cli.pure),cli.scripts,[],exclude_binaries=True,name='arranger-cli',console=True,upx=False,icon=icon)
gui_exe=EXE(PYZ(gui.pure),gui.scripts,[],exclude_binaries=True,name='Sample Arranger',console=False,upx=False,icon=icon)
COLLECT(cli_exe,gui_exe,cli.binaries,cli.datas,gui.binaries,gui.datas,name='SampleArranger',upx=False)
