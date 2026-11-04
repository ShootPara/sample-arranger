"""Keyboard-accessible relative melody pattern editor; no raw code/JSON entry."""
from copy import deepcopy
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QSpinBox,
    QTableWidget,QComboBox,QDialogButtonBox,QPushButton,QHeaderView)
from music import validate_melody_pattern


class RhythmDialog(QDialog):
    def __init__(self,score,parent=None):
        super().__init__(parent);self.setWindowTitle('Melody rhythm');self.resize(620,480)
        self.pattern=None;self.bars=None;layout=QVBoxLayout(self)
        help=QLabel('Shape a repeating one-bar phrase using chord tones and rests. Only melody notes in the selected bars change. Protected notes must survive exactly.');help.setWordWrap(True);layout.addWidget(help)
        selection=QHBoxLayout();self.first=QSpinBox();self.last=QSpinBox()
        for control,name in ((self.first,'First bar'),(self.last,'Last bar')):
            control.setRange(1,score['bars']);control.setAccessibleName(name);selection.addWidget(QLabel(name));selection.addWidget(control)
        self.last.setValue(score['bars']);selection.addStretch();layout.addLayout(selection)
        self.table=QTableWidget(0,3);self.table.setAccessibleName('Melody rhythm cells');self.table.setHorizontalHeaderLabels(['Chord tone / rest','Duration in beats','Velocity'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);layout.addWidget(self.table,1)
        row=QHBoxLayout();add=QPushButton('Add rest');remove=QPushButton('Remove selected cell');row.addWidget(add);row.addWidget(remove);row.addStretch();layout.addLayout(row)
        add.clicked.connect(lambda:self.add_cell({'tone':-1,'ticks':480,'velocity':0}));remove.clicked.connect(self.remove_cell)
        self.feedback=QLabel();self.feedback.setWordWrap(True);self.feedback.setAccessibleName('Pattern timing and validation');layout.addWidget(self.feedback)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.updating=True
        for cell in score.get('melody_pattern',[{'tone':tone,'ticks':960,'velocity':76} for tone in (0,2,1,2)]):self.add_cell(cell)
        self.updating=False;self.update_feedback()

    def add_cell(self,cell):
        if self.table.rowCount()>=16:self.feedback.setText('A phrase supports at most sixteen cells.');return
        row=self.table.rowCount();self.table.insertRow(row)
        tone=QComboBox()
        for text,value in (('Root',0),('Third',1),('Fifth',2),('Rest',-1)):tone.addItem(text,value)
        tone.setCurrentIndex(tone.findData(cell['tone']));tone.setAccessibleName(f'Cell {row+1} chord tone or rest')
        length=QComboBox()
        for ticks in range(120,3841,120):length.addItem(f'{ticks/960:g} beats',ticks)
        length.setCurrentIndex(length.findData(cell['ticks']));length.setAccessibleName(f'Cell {row+1} duration in beats')
        velocity=QSpinBox();velocity.setRange(1,121);velocity.setValue(max(1,cell['velocity']));velocity.setAccessibleName(f'Cell {row+1} velocity')
        for col,control in enumerate((tone,length,velocity)):self.table.setCellWidget(row,col,control)
        def changed(*_):velocity.setEnabled(tone.currentData()!=-1);self.update_feedback()
        tone.currentIndexChanged.connect(changed);length.currentIndexChanged.connect(changed);velocity.valueChanged.connect(changed);changed()

    def remove_cell(self):
        row=self.table.currentRow()
        if row>=0:self.table.removeRow(row);self.update_feedback()

    def value(self):
        result=[]
        for row in range(self.table.rowCount()):
            tone=self.table.cellWidget(row,0).currentData();result.append({'tone':tone,'ticks':self.table.cellWidget(row,1).currentData(),'velocity':0 if tone==-1 else self.table.cellWidget(row,2).value()})
        return result

    def update_feedback(self):
        if getattr(self,'updating',False):return
        pattern=self.value()
        try:validate_melody_pattern(pattern);message='Four beats · ready to apply';valid=True
        except ValueError as error:message=f"{sum(cell['ticks'] for cell in pattern)/960:g} of four beats · {error}";valid=False
        self.feedback.setText(message);self.buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(valid)

    def apply(self):
        if self.first.value()>self.last.value():self.feedback.setText('The first bar must come before the last bar.');return
        try:validate_melody_pattern(self.value())
        except ValueError as error:self.feedback.setText(str(error));return
        self.pattern=deepcopy(self.value());self.bars=list(range(self.first.value()-1,self.last.value()));self.accept()
