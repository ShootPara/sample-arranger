"""Explicit score protections with readable scopes and keyboard table access."""
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QSpinBox,QComboBox,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QPushButton,QDialogButtonBox)
from musical_locks import key


class LockDialog(QDialog):
    def __init__(self,score,parent=None):
        super().__init__(parent);self.setWindowTitle('Protect musical decisions');self.resize(660,480)
        self.selections=[{k:v for k,v in spec.items() if k!='sha256'} for spec in score.get('musical_locks',[])]
        layout=QVBoxLayout(self);label=QLabel('Section protects exact notes, form and harmony. Harmony protects the accepted degree and voicing. Rhythm protects note timing and counts while allowing pitch and velocity edits. These protections apply to the composed score.');label.setWordWrap(True);layout.addWidget(label)
        row=QHBoxLayout();self.first=QSpinBox();self.last=QSpinBox()
        for control,name in ((self.first,'First bar'),(self.last,'Last bar')):control.setRange(1,score['bars']);control.setAccessibleName(name);row.addWidget(QLabel(name));row.addWidget(control)
        self.last.setValue(score['bars']);self.kind=QComboBox();self.kind.addItems(['section','harmony','rhythm']);self.kind.setAccessibleName('Protection kind');row.addWidget(self.kind)
        self.part=QComboBox();self.part.addItems(['all','bass','chords','melody']);self.part.setAccessibleName('Rhythm protection part');self.part.setEnabled(False);row.addWidget(self.part);layout.addLayout(row)
        self.kind.currentTextChanged.connect(lambda value:(self.part.setEnabled(value=='rhythm'),self.part.setCurrentIndex(0)))
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['Bar','Protection','Part']);self.table.setAccessibleName('Protected musical decisions');self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);layout.addWidget(self.table,1)
        row=QHBoxLayout();add=QPushButton('Protect bar range');remove=QPushButton('Unlock selected rows');add.clicked.connect(self.protect);remove.clicked.connect(self.unlock);row.addWidget(add);row.addWidget(remove);row.addStretch();layout.addLayout(row)
        self.feedback=QLabel();self.feedback.setWordWrap(True);layout.addWidget(self.feedback)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons);self.refresh()

    def refresh(self):
        self.selections.sort(key=key);self.table.setRowCount(len(self.selections))
        for row,spec in enumerate(self.selections):
            for column,value in enumerate((spec['bar']+1,spec['kind'].title(),spec['part'].title())):self.table.setItem(row,column,QTableWidgetItem(str(value)))
        self.feedback.setText(f'{len(self.selections)} protections. Save applies them to the workspace; Save project persists them.')

    def protect(self):
        if self.first.value()>self.last.value():self.feedback.setText('Choose a first bar before the last bar.');return
        selected={key(spec):spec for spec in self.selections}
        for bar in range(self.first.value()-1,self.last.value()):
            spec={'bar':bar,'kind':self.kind.currentText(),'part':self.part.currentText() if self.kind.currentText()=='rhythm' else 'all'};selected[key(spec)]=spec
        if len(selected)>512:self.feedback.setText('At most512 protections fit in a project.');return
        self.selections=list(selected.values());self.refresh()

    def unlock(self):
        for row in sorted({index.row() for index in self.table.selectedIndexes()},reverse=True):self.selections.pop(row)
        self.refresh()
