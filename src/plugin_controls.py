"""Controller-provided displays/programs; all plugin work stays in owned workers."""
import math
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QTableWidgetItem,
    QHeaderView,QPushButton,QInputDialog,QComboBox,QSpinBox,QDialogButtonBox)


class ParameterDialog(QDialog):
    def __init__(self,owner,component,arguments,title='Plugin parameters and programs'):
        super().__init__(owner);self.owner=owner;self.values=component['parameters'];self.arguments=arguments;self.loading=False
        self.setWindowTitle(title);self.resize(800,600);layout=QVBoxLayout(self)
        self.status=QLabel('Edit normalized values or convert a displayed value through the plugin. Programs load before explicit overrides; untouched parameters follow the selected program. Save captures component state and independent controller state when the plugin provides it.')
        self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        self.table=QTableWidget(len(self.values),3);self.table.setHorizontalHeaderLabels(['Parameter','Normalized','Plugin display'])
        self.table.setAccessibleName('Plugin parameters with controller provided display values');self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        for row,value in enumerate(self.values):
            for column,text in enumerate((value['name'],str(value['normalized']),value.get('display') or 'Unavailable')):
                item=QTableWidgetItem(text)
                if column!=1 or value['flags']&2:item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable)
                item.setToolTip(f"ID {value['id']} · {value.get('units','')} · {value['steps']} steps"+(" · read only" if value['flags']&2 else ''))
                self.table.setItem(row,column,item)
        self.table.itemChanged.connect(self.changed);layout.addWidget(self.table,1)
        convert=QPushButton('Edit selected displayed value…');convert.setAccessibleName('Convert plugin displayed value to normalized parameter');convert.clicked.connect(self.edit_display);layout.addWidget(convert)
        row=QHBoxLayout();self.lists=QComboBox();self.lists.setAccessibleName('Plugin program list');self.programs=QComboBox();self.programs.setAccessibleName('Named plugin program');self.index=QSpinBox();self.index.setAccessibleName('Zero based plugin program index')
        for listing in component.get('program_lists',[]):self.lists.addItem(listing['name'],listing)
        self.lists.currentIndexChanged.connect(self.select_list);self.programs.currentIndexChanged.connect(lambda i:self.index.setValue(i) if i>=0 else None)
        self.index.valueChanged.connect(lambda i:self.programs.setCurrentIndex(i if i<self.programs.count() else -1))
        self.programs.setPlaceholderText('Name outside bounded inventory')
        row.addWidget(self.lists);row.addWidget(self.programs,1);row.addWidget(QLabel('Index (0-based)'));row.addWidget(self.index);apply=QPushButton('Use program');apply.setAccessibleName('Queue plugin program before parameter overrides');apply.clicked.connect(self.use_program);row.addWidget(apply);layout.addLayout(row)
        self.select_list();apply.setEnabled(self.lists.count()>0)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.validate_accept);layout.addWidget(buttons)

    def changed(self,item):
        if item.column()==1 and not self.loading:self.table.item(item.row(),2).setText('Convert to review edited display')

    def select_list(self):
        listing=self.lists.currentData();self.programs.clear()
        if not listing:self.index.setRange(0,0);self.status.setText(self.status.text()+' No program list was exposed; presets/native editor may provide other choices.');return
        self.programs.addItems([name or f'Unnamed program {i}' for i,name in enumerate(listing['names'])]);self.index.setRange(0,max(0,listing['count']-1))
        selector=next((p for p in self.values if p.get('program_list_id')==listing['id'] and p['steps']==listing['count']-1),None)
        if selector:
            selected=round(selector['normalized']*selector['steps']);self.index.setValue(selected);self.programs.setCurrentIndex(selected if selected<self.programs.count() else -1)
        self.index.setToolTip('Program names are bounded to64 across lists. Use the zero based index for additional programs.')

    def use_program(self):
        listing=self.lists.currentData()
        if not listing or listing['count']<1:return
        matching=[(i,p) for i,p in enumerate(self.values) if p.get('program_list_id')==listing['id'] and not p['flags']&2]
        if len(matching)!=1 or matching[0][1]['steps']!=listing['count']-1:
            self.status.setText('This list has no unambiguous writable program parameter with matching steps. Use the native editor or a vendor preset.');return
        row,parameter=matching[0];value=self.index.value()/parameter['steps'] if parameter['steps'] else 0
        self.convert(row,normalized=value)

    def edit_display(self):
        row=self.table.currentRow()
        if not 0<=row<len(self.values):self.status.setText('Select a parameter first.');return
        if self.values[row]['flags']&2:self.status.setText('The plugin marks this parameter read only.');return
        text,accepted=QInputDialog.getText(self,'Plugin displayed value',self.values[row]['name']+' ('+self.values[row].get('units','')+')',text=self.values[row].get('display') or '')
        if accepted:self.convert(row,display=text)

    def convert(self,row,**value):
        if self.owner.busy:self.status.setText('Wait for the active plugin operation.');return
        parameter=self.values[row]
        def converted(result):
            self.loading=True;self.table.item(row,1).setText(str(result['normalized']));self.table.item(row,2).setText(result['display'] or 'Display unavailable');self.loading=False
            self.status.setText('Plugin conversion accepted. Save commits the program/overrides and captures actual state; Cancel keeps the assignment unchanged.')
            self.owner.message('Plugin conversion ready for review. Save commits state; Cancel preserves the assignment.')
        self.owner.request('plugins.parameter.convert',{**self.arguments,'parameter_id':parameter['id'],**value},converted)

    def edits(self):
        changes={}
        for row,parameter in enumerate(self.values):
            value=float(self.table.item(row,1).text())
            if not math.isfinite(value) or not 0<=value<=1:raise ValueError('Every normalized value must be between zero and one.')
            if value!=parameter['normalized']:
                if parameter['flags']&2:raise ValueError('A read-only plugin parameter cannot be changed.')
                changes[str(parameter['id'])]=value
        if len(changes)>128:raise ValueError('Capture at most128 changed parameters at once.')
        return changes

    def validate_accept(self):
        if self.owner.busy:self.status.setText('Wait for the active conversion or cancel it from the workspace.');return
        try:self.edits();self.accept()
        except ValueError as error:self.status.setText(str(error))
