"""Bounded editable step-automation preview; table remains the keyboard equivalent."""
import math
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QColor,QPen,QBrush,QPainter,QPainterPath
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QComboBox,QGraphicsView,QGraphicsScene,QGraphicsEllipseItem,QGraphicsItem


class Handle(QGraphicsEllipseItem):
    def __init__(self,lane,row,frame,value):
        super().__init__(-5,-5,10,10);self.lane=lane;self.row=row;self.setPos(lane.x(frame),lane.y(value))
        self.setPen(QPen(QColor('#111923'),1));self.setBrush(QBrush(QColor('#85e9dd')))
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable|QGraphicsItem.GraphicsItemFlag.ItemIsSelectable|QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setToolTip(f'{frame/44100:.3f}s · {value:g} normalized · equivalent table row{row+1}')
        self.setZValue(2)
    def itemChange(self,change,value):
        if change==QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            from PySide6.QtCore import QPointF
            return QPointF(min(470,max(50,value.x())),min(132,max(20,value.y())))
        return super().itemChange(change,value)
    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event);self.lane.move_point(self.row,self.pos().x(),self.pos().y())


class View(QGraphicsView):
    def resizeEvent(self,event):
        super().resizeEvent(event);self.fitInView(self.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)


class AutomationLane(QWidget):
    def __init__(self,table,seconds,tempo,parent=None):
        super().__init__(parent);self.table=table;self.seconds=seconds;self.tempo=tempo;self.updating=False;self.handles=[]
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.parameter=QComboBox();self.parameter.setAccessibleName('Displayed automation parameter ID');layout.addWidget(self.parameter)
        self.scene=QGraphicsScene(self);self.scene.setSceneRect(0,0,500,168);self.view=View(self.scene);self.view.setMinimumHeight(145);self.view.setMaximumHeight(210)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing);self.view.setAccessibleName('Editable step automation lane; drag a point or use the equivalent frame ID and value table below');layout.addWidget(self.view)
        self.caption=QLabel('Add parameter points below. Apply automation lane commits the edits.');self.caption.setWordWrap(True);layout.addWidget(self.caption)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(0);self.timer.timeout.connect(self.refresh)
        self.parameter.currentIndexChanged.connect(lambda *_:self.timer.start());table.itemChanged.connect(lambda *_:self.timer.start());seconds.valueChanged.connect(lambda *_:self.timer.start())
        table.model().rowsRemoved.connect(lambda *_:self.timer.start());table.model().rowsInserted.connect(lambda *_:self.timer.start())
        self.refresh()

    def x(self,frame):return 50+420*frame/max(1,round(self.seconds.value()*44100))
    def y(self,value):return 132-112*value
    def parsed(self):
        values=[];invalid=0;end=round(self.seconds.value()*44100);seen=set()
        for row in range(min(self.table.rowCount(),8192)):
            try:
                frame=int(self.table.item(row,0).text());identity=int(self.table.item(row,1).text());value=float(self.table.item(row,2).text())
                if not 0<=frame<=end or not 0<=identity<2**32 or not math.isfinite(value) or not 0<=value<=1:raise ValueError()
                if (frame,identity) in seen:raise ValueError()
                seen.add((frame,identity));values.append((frame,identity,value,row))
            except (ValueError,AttributeError):invalid+=1
        return values,invalid

    def refresh(self):
        values,invalid=self.parsed();selected=self.parameter.currentData();identities=sorted({v[1] for v in values})
        self.parameter.blockSignals(True);self.parameter.clear()
        for identity in identities:self.parameter.addItem('Parameter '+str(identity),identity)
        if selected in identities:self.parameter.setCurrentIndex(identities.index(selected))
        self.parameter.blockSignals(False);selected=self.parameter.currentData()
        self.scene.clear();self.handles=[];self.scene.setBackgroundBrush(QBrush(QColor('#0c131c')))
        for i in range(5):
            y=self.y(i/4);self.scene.addLine(50,y,470,y,QPen(QColor('#304354')));label=self.scene.addText(f'{i/4:g}');label.setDefaultTextColor(QColor('#a9bacb'));label.setPos(4,y-10)
        for i in range(5):
            x=50+105*i;self.scene.addLine(x,20,x,132,QPen(QColor('#233647')));label=self.scene.addText(f'{self.seconds.value()*i/4:g}s');label.setDefaultTextColor(QColor('#a9bacb'));label.setPos(x-12,140)
        points=sorted((v for v in values if v[1]==selected),key=lambda v:(v[0],v[3]));visible=points[:512];path=QPainterPath()
        if visible:
            frame,_,value,_=visible[0];path.moveTo(self.x(frame),self.y(value))
            previous=value
            for frame,_,value,row in visible:
                path.lineTo(self.x(frame),self.y(previous));path.lineTo(self.x(frame),self.y(value));previous=value
                handle=Handle(self,row,frame,value);self.scene.addItem(handle);self.handles.append(handle)
            if len(points)<=512:path.lineTo(470,self.y(previous))
            self.scene.addPath(path,QPen(QColor('#61cbbf'),2))
        message=f'{len(points)} step points · drag snaps to ¼ beat / 0.01 value · Apply commits'
        if len(points)>512:message+=' · first512 shown; table retains all points'
        if invalid:message+=f' · {invalid} invalid/out-of-range rows are hidden, not accepted'
        self.caption.setText(message if values or invalid else 'Add parameter points below. Apply automation lane commits the edits.')
        self.view.fitInView(self.scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)

    def move_point(self,row,x,y):
        if not 0<=row<self.table.rowCount():return
        frames=max(1,round(self.seconds.value()*44100));quantum=60*44100/(self.tempo.value()*4)
        frame=min(frames,max(0,round(((x-50)/420*frames)/quantum)*quantum));value=round(min(1,max(0,(132-y)/112)),2)
        self.table.item(row,0).setText(str(round(frame)));self.table.item(row,2).setText(f'{value:g}');self.table.selectRow(row);self.timer.start()
