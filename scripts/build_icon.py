"""Render the app-owned SVG into private packaging PNG/ICO assets."""
from pathlib import Path
import struct
import sys
from PySide6.QtCore import QByteArray,QBuffer,QIODevice
from PySide6.QtGui import QImage,QPainter
from PySide6.QtSvg import QSvgRenderer

source,destination=map(Path,sys.argv[1:]);destination.mkdir(parents=True,exist_ok=True)
renderer=QSvgRenderer(str(source));images=[]
if not renderer.isValid():raise ValueError('invalid app vector icon')
for size in (16,32,256):
    image=QImage(size,size,QImage.Format.Format_ARGB32);image.fill(0)
    painter=QPainter(image);renderer.render(painter);painter.end()
    data=QByteArray();buffer=QBuffer(data);buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer,'PNG'):raise ValueError('icon rendering failed')
    images.append(bytes(data))
    if size==256:(destination/'arranger.png').write_bytes(images[-1])
offset=6+16*len(images);entries=[]
for size,data in zip((16,32,256),images):
    entries.append(struct.pack('<BBBBHHII',size%256,size%256,0,0,1,32,len(data),offset));offset+=len(data)
(destination/'arranger.ico').write_bytes(struct.pack('<HHH',0,1,len(images))+b''.join(entries)+b''.join(images))
