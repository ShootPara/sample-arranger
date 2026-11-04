"""Desktop editor for the shared, pinned offline routing contract.

Graph editing remains local and validates atomically. Audio/plugin execution uses
the workspace's existing bounded child-command path, never the GUI process.
"""
from copy import deepcopy
import json
from pathlib import Path
import uuid
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QColor,QPen,QBrush,QFont,QPainterPath,QPainter,QAction,QKeySequence
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QSplitter,QWidget,
    QFormLayout,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QComboBox,
    QSpinBox,QDoubleSpinBox,QPushButton,QFileDialog,QInputDialog,QGraphicsView,QGraphicsScene,QTabWidget,QGraphicsItem,QCheckBox,QScrollArea,QMessageBox,QMenu,QGridLayout,QSizePolicy)
from graph import validate_graph


def action(text,callback):
    button=QPushButton(text);button.setAccessibleName(text);button.clicked.connect(callback);return button


class RoutingWorkspace(QDialog):
    def __init__(self,owner,project=None,path=None,proposal=None):
        super().__init__(owner);self.owner=owner;self.setWindowTitle('Sample Arranger · Routing workspace')
        self.resize(1240,790);self.setMinimumSize(1040,680)
        self.graph=deepcopy(project['graph']) if project else {'nodes':[],'outputs':[]}
        self.sources=deepcopy(project['graph_sources']) if project else {}
        self.score=deepcopy(project.get('score')) if project else deepcopy(owner.score)
        self.path=Path(path) if path else None;self.revision=project['revision'] if project else 0
        self.worker=project['worker'] if project else owner.paths['worker'].text()
        self.saved=project;self.loading=False
        self.pending_forms={};self.pending_outputs=None;self.form_name=None;self.form_baseline=None;self.output_baseline=None;self.restoring_forms=False
        self.expected_sources={};self.proposal_brief=None
        if proposal:
            if project:raise ValueError('cannot replace a saved routing project with a proposal')
            self.graph=deepcopy(proposal['graph']);self.sources=deepcopy(proposal['sources']);self.score=None
            self.expected_sources=deepcopy(proposal['source_assets'])
            self.proposal_brief={'initial':owner.initial or owner.brief.text(),'effective':owner.brief.text(),
                                 'ensemble':{key:deepcopy(proposal[key]) for key in ('planner','decisions','missing_roles','warnings','root','mode')}}
        from plan_history import PlanHistory
        self.history=PlanHistory()
        layout=QVBoxLayout(self);header=QHBoxLayout();title=QLabel('ROUTING / MIX');title.setFont(QFont('Segoe UI',20,QFont.Weight.Bold));header.addWidget(title);header.addStretch()
        header.addWidget(action('Fit diagram',self.fit_diagram))
        project_menu=QMenu(self);project_button=QPushButton('Project');project_button.setAccessibleName('Routing project actions');project_button.setMenu(project_menu)
        for caption,callback in (('Open routing project…',self.open),('Package project…',self.package),('Review processing updates',self.review_updates)):project_menu.addAction(caption,callback)
        header.addWidget(project_button);header.addWidget(action('Save routing project',self.save));layout.addLayout(header)
        subtitle=QLabel('Explicit signal paths · compensated plugin buses · local rendering. Select a node to route its input, sidechain and automation.');subtitle.setWordWrap(True);layout.addWidget(subtitle)
        timing=QHBoxLayout();self.seconds=QDoubleSpinBox();self.seconds.setRange(.01,240);self.seconds.setDecimals(3);self.seconds.setValue(project['seconds'] if project else self.score['duration_frames']/44100 if self.score else 12);self.seconds.setAccessibleName('Routing duration in seconds')
        self.tempo=QDoubleSpinBox();self.tempo.setRange(20,400);self.tempo.setValue((project or {}).get('tempo') or owner.bpm.value());self.tempo.setAccessibleName('Routing tempo')
        self.tail=QDoubleSpinBox();self.tail.setRange(0,1);self.tail.setDecimals(3);self.tail.setValue((project or {}).get('tail_seconds',0));self.tail.setAccessibleName('Retained routing tail seconds')
        if proposal:self.seconds.setValue(proposal['seconds']);self.tempo.setValue(proposal['tempo'])
        for caption,control in (('Duration',self.seconds),('BPM',self.tempo),('Tail (s)',self.tail)):timing.addWidget(QLabel(caption));timing.addWidget(control)
        timing.addWidget(action('Choose host engine…',self.choose_worker));timing.addStretch();timing.addWidget(action('Undo routing edit',self.undo));timing.addWidget(action('Redo routing edit',lambda:self.undo(True)));layout.addLayout(timing)
        split=QSplitter(Qt.Orientation.Horizontal);layout.addWidget(split,1)
        left=QWidget();box=QVBoxLayout(left);box.addWidget(QLabel('SOURCES & PROCESSORS'))
        self.items=QTableWidget(0,2);self.items.setHorizontalHeaderLabels(['Name','Kind']);self.items.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.items.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.items.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.items.setAccessibleName('Routing sources and processors');self.items.itemSelectionChanged.connect(self.select);box.addWidget(self.items)
        for caption,entries in (('Add source',(('Audio file…',self.add_source),('Generated silence',self.add_silence))),
                                ('Add processor',(('VST3 module file…',self.add_plugin),('VST3 bundle folder…',lambda:self.add_plugin(True)),('Mixer',self.add_mixer)))):
            menu=QMenu(self);control=QPushButton(caption);control.setAccessibleName(caption);control.setMenu(menu)
            for text,callback in entries:menu.addAction(text,callback)
            box.addWidget(control)
        box.addWidget(action('Remove selected',self.remove))
        split.addWidget(left)
        self.scene=QGraphicsScene(self);self.scene.selectionChanged.connect(self.diagram_selected);self.view=QGraphicsView(self.scene);self.view.setRenderHint(QPainter.RenderHint.Antialiasing);self.view.setAccessibleName('Routing diagram; equivalent editable controls in processor inspector');split.addWidget(self.view)
        right=QWidget();box=QVBoxLayout(right);self.selection=QLabel('Select a processor');self.selection.setWordWrap(True);box.addWidget(self.selection)
        self.tabs=QTabWidget();self.tabs.setMinimumWidth(300)
        inspector_scroll=QScrollArea();inspector_scroll.setWidgetResizable(True);inspector_scroll.setWidget(self.tabs);inspector_scroll.setMinimumSize(0,0);inspector_scroll.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored);box.addWidget(inspector_scroll,1);box.addWidget(action('Restore applied inspector values',self.restore_inspector))
        routes=QWidget();properties=QVBoxLayout(routes);self.processor_controls=QWidget();form=QFormLayout(self.processor_controls);self.input=QComboBox();self.sidechain=QComboBox();self.input_bus=QSpinBox();self.side_bus=QSpinBox()
        for control in (self.input_bus,self.side_bus):control.setRange(0,7)
        for caption,control in (('Main source',self.input),('Main bus',self.input_bus),('Sidechain source',self.sidechain),('Sidechain bus',self.side_bus)):
            control.setAccessibleName(caption);form.addRow(caption,control)
        form.addRow(action('Apply input routes',self.apply_routes))
        self.part=QComboBox();self.part.addItems(['External MIDI / no score','bass','chords','melody']);self.part.setAccessibleName('Node score intention part');form.addRow('Score part',self.part)
        form.addRow(action('Use score part',self.use_part));form.addRow(action('Choose MIDI note file…',self.choose_notes))
        form.addRow(action('Open native plugin editor',self.native_editor));self.state=QLabel('No selected state');self.state.setWordWrap(True);form.addRow(self.state)
        form.addRow(action('Parameters / programs…',self.parameter_controls))
        form.addRow(action('Locate plugin module…',self.locate_plugin));form.addRow(action('Locate plugin bundle…',lambda:self.locate_plugin(True)))
        properties.addWidget(self.processor_controls)
        self.source_controls=QWidget();source_form=QFormLayout(self.source_controls);self.source_info=QLabel();self.source_info.setWordWrap(True);source_form.addRow(self.source_info)
        self.loop=QCheckBox('Repeat selected audio source');self.loop.setAccessibleName('Repeat selected routing audio source');source_form.addRow(self.loop);source_form.addRow(action('Apply source repetition',self.apply_source))
        self.offset=QDoubleSpinBox();self.offset.setRange(0,239.999);self.offset.setDecimals(3);self.offset.setSuffix(' s');self.offset.setAccessibleName('Selected audio source start');source_form.addRow('Source start',self.offset);source_form.addRow(action('Apply source start',self.apply_offset));source_form.addRow(action('Source tempo / half-double…',self.match_source));source_form.addRow(action('Relocate selected source…',self.relocate));properties.addWidget(self.source_controls)
        self.property_hint=QLabel('Select a source or processor to see its relevant controls. Mixer input routes have their own tab.');self.property_hint.setWordWrap(True);properties.addWidget(self.property_hint);properties.addStretch()
        route_scroll=QScrollArea();route_scroll.setWidgetResizable(True);route_scroll.setWidget(routes);self.tabs.addTab(route_scroll,'Properties')
        self.automation=QTableWidget(0,3);self.automation.setHorizontalHeaderLabels(['Frame','Parameter ID','Value 0–1']);self.automation.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);self.automation.setAccessibleName('Editable normalized automation points')
        panel=QWidget();box2=QVBoxLayout(panel);hint=QLabel('Step points at44.1kHz. Parameter IDs come from the plugin; native rendering rejects unavailable/read-only IDs. External automation is replaced only on Apply.');hint.setWordWrap(True);box2.addWidget(hint)
        from automation_lane import AutomationLane
        self.automation_lane=AutomationLane(self.automation,self.seconds,self.tempo,self);box2.addWidget(self.automation_lane);box2.addWidget(self.automation)
        row=QHBoxLayout();row.addWidget(action('Add point',lambda:self.add_row(self.automation,['0','1','1'])));row.addWidget(action('Remove point',lambda:self.automation.removeRow(self.automation.currentRow())));box2.addLayout(row);box2.addWidget(action('Inspect parameter IDs',self.inspect_parameters));box2.addWidget(action('Apply automation lane',self.apply_automation));self.tabs.addTab(panel,'Automation')
        self.mix=QTableWidget(0,3);self.mix.setHorizontalHeaderLabels(['Source / node','Bus','Gain']);self.mix.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);self.mix.setAccessibleName('Mixer input routes')
        panel=QWidget();box2=QVBoxLayout(panel);box2.addWidget(self.mix);box2.addWidget(action('Add mixer input',lambda:self.add_row(self.mix,[next(iter(self.sources),'source'),'0','1'])));box2.addWidget(action('Remove mixer input',lambda:self.mix.removeRow(self.mix.currentRow())));box2.addWidget(action('Apply mixer inputs',self.apply_mix));self.tabs.addTab(panel,'Mixer');split.addWidget(right);split.setSizes([250,590,360])
        output=QHBoxLayout();output.addWidget(QLabel('MASTER OUTPUTS'))
        self.outputs=QTableWidget(0,3);self.outputs.setHorizontalHeaderLabels(['Source / node','Bus','Gain']);self.outputs.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);self.outputs.setMaximumHeight(130);self.outputs.setAccessibleName('Master output routes');output.addWidget(self.outputs,1)
        controls=QGridLayout()
        for i,(caption,callback) in enumerate((('Add output',self.add_output),('Remove output',lambda:self.outputs.removeRow(self.outputs.currentRow())),('Apply outputs',self.apply_outputs),('Restore applied outputs',self.restore_outputs))):controls.addWidget(action(caption,callback),i//2,i%2)
        output.addLayout(controls);layout.addLayout(output)
        self.status=QLabel('Choose sources and processors. All edits stay local until saved.');self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        transport=QHBoxLayout();transport.addWidget(action('Play last result',owner.preview));transport.addWidget(action('Stop preview',owner.stop_preview));transport.addStretch();transport.addWidget(action('Cancel job',owner.cancel));transport.addWidget(action('Save & render MP3',self.render));transport.addWidget(action('Close routing',self.reject));layout.addLayout(transport)
        self.shortcuts=[]
        for key,callback in (('Ctrl+S',self.save),('Ctrl+O',self.open),('Ctrl+Return',self.render),('Ctrl+Z',self.undo),('Ctrl+Y',lambda:self.undo(True))):
            shortcut=QAction(self);shortcut.setShortcut(QKeySequence(key));shortcut.triggered.connect(lambda checked=False,fn=callback:fn());self.addAction(shortcut);self.shortcuts.append(shortcut)
        self.refresh()
        for table in (self.automation,self.mix,self.outputs):table.itemChanged.connect(lambda *_:self.capture_pending())
        for control in (self.input,self.sidechain,self.part):control.currentIndexChanged.connect(lambda *_:self.capture_pending())
        for control in (self.input_bus,self.side_bus,self.offset):control.valueChanged.connect(lambda *_:self.capture_pending())
        self.loop.toggled.connect(lambda *_:self.capture_pending())
        QTimer.singleShot(0,self.fit_diagram)
        self.was_busy=False;self.progress_timer=QTimer(self);self.progress_timer.setInterval(200);self.progress_timer.timeout.connect(self.sync_progress);self.progress_timer.start()

    def sync_progress(self):
        if self.owner.busy or self.was_busy:self.status.setText(self.owner.state.text())
        self.was_busy=self.owner.busy

    def reject(self):
        if self.owner.busy:self.status.setText('Cancel or wait for the active operation before closing routing.');return
        if not self.guard_unsaved(self.reject):return
        super().reject()

    def table_values(self,table):
        return [[table.item(row,col).text() if table.item(row,col) else '' for col in range(table.columnCount())] for row in range(table.rowCount())]
    def set_table_values(self,table,values):
        table.setRowCount(0)
        for row in values:self.add_row(table,row)
    def inspector_values(self):
        return {'input':self.input.currentText(),'input_bus':self.input_bus.value(),'sidechain':self.sidechain.currentText(),
                'side_bus':self.side_bus.value(),'part':self.part.currentIndex(),'loop':self.loop.isChecked(),'offset':self.offset.value(),
                'automation':self.table_values(self.automation),'mix':self.table_values(self.mix)}
    def set_inspector_values(self,value):
        self.input.setCurrentText(value['input']);self.input_bus.setValue(value['input_bus']);self.sidechain.setCurrentText(value['sidechain']);self.side_bus.setValue(value['side_bus'])
        self.part.setCurrentIndex(value['part']);self.loop.setChecked(value['loop']);self.offset.setValue(value['offset'])
        self.set_table_values(self.automation,value['automation']);self.set_table_values(self.mix,value['mix'])
    def capture_pending(self):
        if self.restoring_forms:return
        if self.form_name is not None and self.form_baseline is not None:
            value=self.inspector_values()
            changes={k:v for k,v in value.items() if v!=self.form_baseline[k]}
            if changes:self.pending_forms[self.form_name]=changes
            else:self.pending_forms.pop(self.form_name,None)
        if self.output_baseline is not None:
            values=self.table_values(self.outputs);self.pending_outputs=values if values!=self.output_baseline else None
    def has_pending(self):
        self.capture_pending();return bool(self.pending_forms or self.pending_outputs is not None)
    def restore_inspector(self):
        self.pending_forms.pop(self.form_name,None)
        self.restoring_forms=True
        try:
            if self.form_baseline is not None:self.set_inspector_values(self.form_baseline)
        finally:self.restoring_forms=False
        self.message('Selected inspector restored to applied values. Other pending panels are preserved.')
    def restore_outputs(self):
        self.pending_outputs=None;self.restoring_forms=True
        try:self.set_table_values(self.outputs,self.output_baseline or [])
        finally:self.restoring_forms=False
        self.message('Master outputs restored to applied routes. Pending inspector panels are preserved.')

    def has_changes(self):
        if self.has_pending():return True
        if not self.saved:return bool(self.graph['nodes'] or self.sources)
        return (self.graph!=self.saved['graph'] or self.sources!=self.saved['graph_sources'] or self.score!=self.saved.get('score')
                or self.worker!=self.saved['worker']
                or abs(self.seconds.value()-self.saved['seconds'])>.0005 or self.tempo.value()!=(self.saved['tempo'] or 120)
                or self.tail.value()!=self.saved['tail_seconds'])
    def guard_unsaved(self,continuation):
        if not self.has_changes():return True
        choice=QMessageBox.question(self,'Unsaved routing changes','Save your routing changes before leaving this project?',
                                   QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Save)
        if choice==QMessageBox.StandardButton.Save:self.save(continuation);return False
        return choice==QMessageBox.StandardButton.Discard
    def undo(self,redo=False):
        if self.owner.busy:self.message('Wait for active processing before changing edit history.');return
        state=(self.history.redo if redo else self.history.undo)({'graph':self.graph,'sources':self.sources})
        if state is None:self.message('No further routing edits to '+('redo.' if redo else 'undo.'));return
        self.graph=state['graph'];self.sources=state['sources'];self.refresh();self.message('Routing edit '+('redone.' if redo else 'undone.'))

    def message(self,text):self.status.setText(str(text));self.owner.message(text)
    def selected(self):
        row=self.items.currentRow()
        return self.items.item(row,0).text() if row>=0 and self.items.item(row,0) else None
    def node(self):return next((node for node in self.graph['nodes'] if node['id']==self.selected()),None)
    def add_row(self,table,values):
        limit=8192 if table is self.automation else 16
        if table.rowCount()>=limit:
            if hasattr(self,'status'):self.message(f'This panel supports at most{limit} rows.')
            return
        row=table.rowCount();table.insertRow(row)
        for column,value in enumerate(values):table.setItem(row,column,QTableWidgetItem(str(value)))
    def fill_routes(self,table,values):
        table.setRowCount(0)
        for value in values:self.add_row(table,[value['node'],value['bus'],value.get('gain',1)])
    def read_routes(self,table):
        return [{'node':table.item(row,0).text(),'bus':int(table.item(row,1).text()),'gain':float(table.item(row,2).text())} for row in range(table.rowCount())]
    def commit(self,graph=None,sources=None,applied_fields=(),applied_outputs=False):
        if self.owner.busy:self.message('Wait for the active operation before editing routing.');return
        candidate=deepcopy(graph if graph is not None else self.graph);assets=deepcopy(sources if sources is not None else self.sources)
        # Incomplete empty scenes are editable; a nonempty published graph is strict.
        if candidate['nodes'] and candidate['outputs']:validate_graph(candidate,assets)
        if candidate!=self.graph or assets!=self.sources:self.history.remember({'graph':self.graph,'sources':self.sources})
        self.capture_pending()
        if self.form_baseline is not None:
            values=self.inspector_values()
            for field in applied_fields:
                self.form_baseline[field]=values[field]
                self.pending_forms.get(self.form_name,{}).pop(field,None)
            if not self.pending_forms.get(self.form_name):self.pending_forms.pop(self.form_name,None)
        if applied_outputs:self.output_baseline=self.table_values(self.outputs);self.pending_outputs=None
        self.graph=candidate;self.sources=assets;self.refresh();self.message('Routing edit applied. Save to persist this revision.')
    def refresh(self):
        self.capture_pending();previous_restore=self.restoring_forms;self.restoring_forms=True
        try:
            chosen=self.selected();self.items.blockSignals(True);self.items.setRowCount(0)
            names=list(self.sources)+[node['id'] for node in self.graph['nodes']]
            for name in names:
                node=next((n for n in self.graph['nodes'] if n['id']==name),None)
                self.add_row(self.items,[name,('Mixer' if 'mix' in node else 'VST3') if node else 'Silence' if 'silence' in self.sources[name] else 'Audio'])
                self.items.item(self.items.rowCount()-1,0).setToolTip(str(node.get('plugin','')) if node else self.sources[name].get('file','Generated silence'))
            self.items.blockSignals(False)
            if chosen in names:self.items.selectRow(names.index(chosen))
            self.fill_routes(self.outputs,self.graph['outputs']);self.draw();self.select()
            self.output_baseline=self.table_values(self.outputs)
            if self.pending_outputs is not None:
                self.set_table_values(self.outputs,self.pending_outputs)
                if self.table_values(self.outputs)==self.output_baseline:self.pending_outputs=None
            names=set(self.sources)|{node['id'] for node in self.graph['nodes']}
            self.pending_forms={key:value for key,value in self.pending_forms.items() if key in names}
        finally:self.restoring_forms=previous_restore

    def draw(self):
        self.scene.blockSignals(True);self.scene.clear();positions={};layers={name:0 for name in self.sources}
        try:ordered=validate_graph(self.graph,self.sources)
        except ValueError:ordered=self.graph['nodes']
        for node in ordered:
            refs=node['mix'] if 'mix' in node else [node['input']]+([node['sidechain']] if 'sidechain' in node else [])
            layers[node['id']]=1+max((layers.get(ref['node'],0) for ref in refs),default=0)
        rows={}
        for name,layer in layers.items():
            row=rows.get(layer,0);rows[layer]=row+1;x=20+layer*235;y=40+row*115;positions[name]=(x,y)
            node=next((n for n in ordered if n['id']==name),None);kind='SUM / MIX' if node and 'mix' in node else 'VST3 PROCESSOR' if node else 'SILENCE' if 'silence' in self.sources[name] else 'AUDIO SOURCE'
            rect=self.scene.addRect(x,y,175,66,QPen(QColor('#61cbbf')),QBrush(QColor('#214e5c') if node else QColor('#233647')));rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable);rect.setData(0,name)
            label=self.scene.addText(name);label.setDefaultTextColor(QColor('#e5edf4'));label.setPos(x+9,y+5)
            detail=self.scene.addText(kind);detail.setDefaultTextColor(QColor('#a9bacb'));detail.setFont(QFont('Segoe UI',8));detail.setPos(x+9,y+31)
        def line(ref,destination,side=False):
            if ref['node'] not in positions:return
            x,y=positions[ref['node']];dx,dy=destination
            path=QPainterPath();path.moveTo(x+175,y+33);path.cubicTo(x+205,y+33,dx-30,dy+33,dx,dy+33)
            edge=self.scene.addPath(path,QPen(QColor('#e7c573') if side else QColor('#79ddd0'),2));edge.setZValue(-1)
            label=self.scene.addText(('KEY ' if side else 'BUS ')+str(ref['bus']));label.setDefaultTextColor(QColor('#e7c573') if side else QColor('#a9bacb'));label.setFont(QFont('Segoe UI',8));label.setPos((x+175+dx)/2-15,(y+dy)/2+11)
        for node in ordered:
            refs=node['mix'] if 'mix' in node else [node['input']]+([node['sidechain']] if 'sidechain' in node else [])
            for ref in refs:
                line(ref,positions[node['id']],ref is node.get('sidechain'))
        master=(20+(max(layers.values(),default=0)+1)*235,40)
        if self.graph['outputs']:
            self.scene.addRect(*master,175,66,QPen(QColor('#e7c573')),QBrush(QColor('#3d3530')));label=self.scene.addText('MASTER / MP3');label.setDefaultTextColor(QColor('#f4e2b0'));label.setPos(master[0]+9,master[1]+15)
            for ref in self.graph['outputs']:line(ref,master)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-10,-10,20,20))
        self.scene.blockSignals(False)
    def diagram_selected(self):
        selected=self.scene.selectedItems()
        if len(selected)!=1:return
        name=selected[0].data(0)
        for row in range(self.items.rowCount()):
            if self.items.item(row,0).text()==name:self.items.selectRow(row);return
    def fit_diagram(self):
        rect=self.scene.sceneRect();self.view.resetTransform()
        if rect.width()>0 and rect.height()>0:
            scale=min(1,max(.65,min((self.view.viewport().width()-16)/rect.width(),(self.view.viewport().height()-16)/rect.height())))
            self.view.scale(scale,scale);self.view.centerOn(rect.center())
    def select(self):
        self.capture_pending();previous_restore=self.restoring_forms;self.restoring_forms=True
        try:
            node=self.node();name=self.selected();self.selection.setText(name or 'Select a source or processor');self.input.clear();self.sidechain.clear();self.sidechain.addItem('None')
            processor=bool(node and 'mix' not in node);mixer=bool(node and 'mix' in node);file_source=name in self.sources and 'file' in self.sources[name]
            self.processor_controls.setVisible(processor);self.source_controls.setVisible(file_source);self.property_hint.setVisible(not processor and not file_source)
            self.tabs.setTabEnabled(1,processor);self.tabs.setTabEnabled(2,mixer)
            if mixer:self.tabs.setCurrentIndex(2)
            elif self.tabs.currentIndex()==2 or not processor:self.tabs.setCurrentIndex(0)
            if file_source:
                spec=self.sources[name];text=Path(spec['file']).name
                if 'source_bpm' in spec:text+=f"\n{spec['source_bpm']:g} BPM ×{spec['beat_scale']:g} → {spec['target_bpm']:g} BPM"
                else:text+='\nOriginal speed · no tempo interpretation applied'
                self.source_info.setText(text);self.source_info.setToolTip(spec['file'])
            names=list(self.sources)+[n['id'] for n in self.graph['nodes'] if n['id']!=name];self.input.addItems(names);self.sidechain.addItems(names);self.automation.setRowCount(0);self.mix.setRowCount(0)
            self.loop.setEnabled(name in self.sources and 'file' in self.sources[name]);self.loop.setChecked(self.sources.get(name,{}).get('loop',False))
            self.offset.setEnabled(self.loop.isEnabled());self.offset.setValue(self.sources.get(name,{}).get('offset_seconds',0))
            if node and 'mix' not in node:
                self.input.setCurrentText(node['input']['node']);self.input_bus.setValue(node['input']['bus']);self.sidechain.setCurrentText(node.get('sidechain',{}).get('node','None'));self.side_bus.setValue(node.get('sidechain',{}).get('bus',0));self.part.setCurrentIndex(['','bass','chords','melody'].index(node.get('score_part','')))
                self.state.setText('State: '+Path(node['state']).parent.name if node.get('state') else 'Default plugin state. No preset captured.')
                for point in node.get('automation_points',[]):self.add_row(self.automation,[point['frame'],point['id'],point['value']])
            elif node:self.fill_routes(self.mix,node['mix'])
            self.form_name=name;self.form_baseline=self.inspector_values()
            if name in self.pending_forms:
                self.set_inspector_values({**self.form_baseline,**self.pending_forms[name]})
                if self.inspector_values()==self.form_baseline:self.pending_forms.pop(name,None)
            self.automation_lane.timer.start()
        finally:self.restoring_forms=previous_restore

    def name(self,prefix):
        existing=set(self.sources)|{n['id'] for n in self.graph['nodes']}
        return next(prefix+str(i) for i in range(1,100) if prefix+str(i) not in existing)
    def add_source(self):
        path=QFileDialog.getOpenFileName(self,'Choose local audio source')[0]
        if not path:return
        if len(self.sources)>=8:self.message('At most8 sources are supported.');return
        sources=deepcopy(self.sources);sources[self.name('audio')]={'file':path,'loop':False};self.commit(sources=sources)
    def add_silence(self):
        if len(self.sources)>=8:self.message('At most8 sources are supported.');return
        sources=deepcopy(self.sources);sources[self.name('silence')]={'silence':True};self.commit(sources=sources)
    def add_plugin(self,folder=False):
        if self.owner.busy:return
        if not self.sources:self.message('Add an audio or silence source before a processor.');return
        if len(self.graph['nodes'])>=8:self.message('At most8 processors/mixers are supported.');return
        path=QFileDialog.getExistingDirectory(self,'Choose installed .vst3 bundle folder') if folder else QFileDialog.getOpenFileName(self,'Choose installed VST3 module',filter='VST3 modules (*.vst3)')[0]
        if not path:return
        if Path(path).suffix.lower()!='.vst3':self.message('Select the actual .vst3 bundle folder/module, not its parent installation folder.');return
        def loaded(report):
            values=[item for item in report['classes'] if 1<=item['audio_outputs']<=8 and 0<=item['audio_inputs']<=2]
            if not values:self.message('No supported audio processor component found.');return
            labels=[f"{index+1}. {item['name']} · {item['audio_inputs']} in / {item['audio_outputs']} out" for index,item in enumerate(values)]
            label,ok=QInputDialog.getItem(self,'Choose component','Processor',labels,0,False)
            if not ok:return
            component=values[labels.index(label)];graph=deepcopy(self.graph);name=self.name('processor')
            graph['nodes'].append({'id':name,'plugin':path,'class_id':component['class_id'],'input':{'node':next(iter(self.sources)),'bus':0}})
            if not graph['outputs']:graph['outputs']=[{'node':name,'bus':0,'gain':1}]
            self.commit(graph);self.items.selectRow(len(self.sources)+len(graph['nodes'])-1)
        self.owner.request('plugins.inspect',{'worker':self.worker,'plugin':path},loaded)
    def add_mixer(self):
        if not self.sources or len(self.graph['nodes'])>=8:self.message('Add a source first; at most8 nodes are supported.');return
        graph=deepcopy(self.graph);name=self.name('mix');graph['nodes'].append({'id':name,'mix':[{'node':next(iter(self.sources)),'bus':0,'gain':1}]})
        if not graph['outputs']:graph['outputs']=[{'node':name,'bus':0,'gain':1}]
        self.commit(graph)
    def remove(self):
        name=self.selected()
        if not name:return
        graph=deepcopy(self.graph);sources=deepcopy(self.sources);sources.pop(name,None);graph['nodes']=[n for n in graph['nodes'] if n['id']!=name]
        try:self.commit(graph,sources)
        except ValueError as error:self.message('Remove or reroute references first. '+str(error))
    def modify(self,callback,applied_fields=()):
        if self.owner.busy:self.message('Wait for the active operation before editing routing.');return
        node=self.node()
        if not node:self.message('Select a processor first.');return
        graph=deepcopy(self.graph);target=next(n for n in graph['nodes'] if n['id']==node['id'])
        try:callback(target);self.commit(graph,applied_fields=applied_fields)
        except (ValueError,AttributeError,TypeError) as error:self.message(error)
    def apply_routes(self):
        def change(node):
            if 'mix' in node:raise ValueError('Use the Mixer tab for mixer inputs.')
            node['input']={'node':self.input.currentText(),'bus':self.input_bus.value()};node.pop('sidechain',None)
            if self.sidechain.currentText()!='None':node['sidechain']={'node':self.sidechain.currentText(),'bus':self.side_bus.value()}
        self.modify(change,('input','input_bus','sidechain','side_bus'))
    def apply_source(self):
        name=self.selected()
        if name not in self.sources or 'file' not in self.sources[name]:self.message('Select a file source first.');return
        sources=deepcopy(self.sources);sources[name]['loop']=self.loop.isChecked();self.commit(sources=sources,applied_fields=('loop',))
    def apply_offset(self):
        name=self.selected()
        if name not in self.sources or 'file' not in self.sources[name]:self.message('Select a file source first.');return
        if self.offset.value()>=self.seconds.value():self.message('Place the source before the arrangement ends.');return
        sources=deepcopy(self.sources);sources[name]['offset_seconds']=self.offset.value();self.commit(sources=sources,applied_fields=('offset',))
    def match_source(self):
        name=self.selected()
        if name not in self.sources or 'file' not in self.sources[name] or self.owner.busy:self.message('Select a file source first.');return
        dialog=QDialog(self);dialog.setWindowTitle('Review source tempo interpretation');form=QFormLayout(dialog)
        label=QLabel('Choose the source BPM and beat interpretation explicitly. The original file and catalog hints are preserved; pitch is preserved with bounded time stretching.');label.setWordWrap(True);form.addRow(label)
        source=QDoubleSpinBox();source.setRange(20,400);source.setValue(self.sources[name].get('source_bpm',self.tempo.value()));source.setAccessibleName('Source original BPM');form.addRow('Source BPM',source)
        scale=QComboBox();scale.addItems(['Normal beat count ×1','Half-time beat count ×0.5','Double-time beat count ×2']);scale.setCurrentIndex([1,.5,2].index(self.sources[name].get('beat_scale',1)));scale.setAccessibleName('Source half or double time interpretation');form.addRow('Interpretation',scale)
        form.addRow(QLabel(f'Project target: {self.tempo.value():g} BPM. Supported speed0.5–2.'))
        def apply():
            sources=deepcopy(self.sources);sources[name].update(source_bpm=source.value(),target_bpm=self.tempo.value(),beat_scale=[1,.5,2][scale.currentIndex()])
            try:
                from graph import validate_source_specs
                validate_source_specs(sources);self.commit(sources=sources);dialog.accept()
            except ValueError as error:label.setText(str(error))
        def clear():
            sources=deepcopy(self.sources)
            for key in ('source_bpm','target_bpm','beat_scale'):sources[name].pop(key,None)
            self.commit(sources=sources);dialog.accept()
        form.addRow(action('Apply reviewed tempo',apply));form.addRow(action('Use original source speed',clear));form.addRow(action('Cancel tempo change',dialog.reject));dialog.exec()
    def use_part(self):
        def change(node):
            if 'mix' in node:raise ValueError('A mixer cannot consume MIDI.')
            node.pop('score_part',None)
            if self.part.currentIndex():
                if not self.score:raise ValueError('Build a composed plan in the main workspace first.')
                node.pop('notes',None);node['score_part']=self.part.currentText()
        self.modify(change,('part',))
    def choose_notes(self):
        path=QFileDialog.getOpenFileName(self,'Choose MIDI intention rows (start end pitch velocity)')[0]
        if path:self.modify(lambda node:(node.pop('score_part',None),node.update(notes=path)))
    def apply_automation(self):
        def change(node):
            if 'mix' in node:raise ValueError('Plugin automation requires a VST3 processor.')
            points=[{'frame':int(self.automation.item(row,0).text()),'id':int(self.automation.item(row,1).text()),'value':float(self.automation.item(row,2).text())} for row in range(self.automation.rowCount())]
            node.pop('automation',None);node['automation_points']=sorted(points,key=lambda point:(point['frame'],point['id']))
        self.modify(change,('automation',))
    def apply_mix(self):
        def change(node):
            if 'mix' not in node:raise ValueError('Select a mixer node first.')
            node['mix']=self.read_routes(self.mix)
        self.modify(change,('mix',))
    def add_output(self):self.add_row(self.outputs,[self.selected() or next(iter(self.sources),'source'),'0','1'])
    def apply_outputs(self):
        try:graph=deepcopy(self.graph);graph['outputs']=self.read_routes(self.outputs);self.commit(graph,applied_outputs=True)
        except (ValueError,AttributeError) as error:self.message(error)
    def native_editor(self):
        node=self.node()
        if not node or 'mix' in node or self.owner.busy:self.message('Select a VST3 processor.');return
        from workspace import DATA
        arguments={'worker':self.worker,'plugin':node['plugin'],'class_id':node['class_id'],'presets':str(DATA/'presets')}
        if node.get('state'):arguments['state']=node['state']
        def captured(result):
            graph=deepcopy(self.graph);target=next(item for item in graph['nodes'] if item['id']==node['id']);target['state']=result['state'];self.commit(graph);self.message('Plugin state captured. Save the routing project to pin it.')
        self.owner.request('plugins.edit',arguments,captured)
    def inspect_parameters(self):
        node=self.node()
        if not node or 'mix' in node or self.owner.busy:self.message('Select a VST3 processor.');return
        arguments={'worker':self.worker,'plugin':node['plugin'],'class_id':node['class_id']}
        if node.get('state'):arguments['state']=node['state']
        def loaded(report):
            component=next(item for item in report['classes'] if item['class_id']==node['class_id'])
            dialog=QDialog(self);dialog.setWindowTitle('Processor parameter IDs');dialog.resize(650,420);box=QVBoxLayout(dialog)
            label=QLabel(component['name']+' · normalized automation values. Read-only IDs cannot be automated.');label.setWordWrap(True);box.addWidget(label)
            table=QTableWidget(0,4);table.setHorizontalHeaderLabels(['ID','Parameter','Value','Read-only']);table.setAccessibleName('Native processor parameter inventory');table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch);table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            for parameter in component['parameters']:self.add_row(table,[parameter['id'],parameter['name'],parameter['normalized'],'Yes' if parameter['flags']&2 else 'No'])
            box.addWidget(table);box.addWidget(action('Close parameters',dialog.accept));dialog.exec()
        self.owner.request('plugins.inspect',arguments,loaded)
    def parameter_controls(self):
        node=self.node()
        if not node or 'mix' in node or self.owner.busy:self.message('Select a VST3 processor.');return
        node_id=node['id'];arguments={'worker':self.worker,'plugin':node['plugin'],'class_id':node['class_id']}
        if node.get('state'):arguments['state']=node['state']
        def captured(result):
            graph=deepcopy(self.graph);target=next((item for item in graph['nodes'] if item['id']==node_id),None)
            if target is None or target.get('plugin')!=arguments['plugin'] or target.get('class_id')!=arguments['class_id']:self.message('Processor assignment changed; captured preset was not attached.');return
            target['state']=result['state'];self.commit(graph);self.message('Program/parameter state captured. Save to pin component state'+(' and controller state.' if result.get('controller_sha256') else '; this plugin provides no independent controller state.'))
        self.owner.edit_parameter_state(arguments,'Routing processor parameters / programs',captured)
    def locate_plugin(self,bundle=False):
        node=self.node()
        if not node or 'mix' in node or self.owner.busy:self.message('Select a VST3 processor and finish active work first.');return
        path=QFileDialog.getExistingDirectory(self,'Locate installed VST3 bundle') if bundle else QFileDialog.getOpenFileName(self,'Locate installed VST3 module',filter='VST3 module (*.vst3)')[0]
        if not path:return
        node_id=node['id'];class_id=node['class_id']
        def inspected(report):
            if class_id not in {item['class_id'] for item in report['classes']}:self.message('This bundle does not contain the saved component. Routing and state are unchanged.');return
            graph=deepcopy(self.graph);target=next((item for item in graph['nodes'] if item['id']==node_id),None)
            if target is None or target.get('class_id')!=class_id:self.message('Processor changed before recovery completed; selection was not attached.');return
            target['plugin']=str(Path(path).resolve());self.commit(graph);self.message('Installed component located. Save pins this explicit selection; render checks state compatibility. Opaque libraries and activation remain separate.')
        self.owner.request('plugins.inspect',{'worker':self.worker,'plugin':path,'class_id':class_id},inspected)
    def relocate(self):
        name=self.selected()
        if not self.path or name not in self.sources or 'file' not in self.sources[name]:self.message('Save this routing project and select a file source first.');return
        path=QFileDialog.getOpenFileName(self,'Relocate identical source content')[0]
        if not path:return
        def loaded(report):
            self.sources[name]=report['project']['graph_sources'][name];self.revision=report['project']['revision'];self.saved=report['project'];self.refresh();self.message('Identical source relocated. Other workspace edits remain unsaved.')
        self.owner.request('project.graph.relink',{'project':str(self.path),'expected_revision':self.revision,'replacements':{name:path}},loaded)
    def review_updates(self):
        if not self.path or self.owner.busy:self.message('Save/open the routing project and wait for active work first.');return
        def reviewed(report):
            if report['revision']!=self.revision:self.message('The saved revision changed. Reopen before reviewing processing.');return
            if not report['changes']:self.message('Saved processing/source content is unchanged.');return
            dialog=QDialog(self);dialog.setWindowTitle('Review exact routing processing updates');dialog.resize(800,430);box=QVBoxLayout(dialog)
            label=QLabel('Select changed processing files to adopt. Hash review is not compatibility certification. Missing files and changed source audio cannot be adopted; relocate identical audio or select replacement content in a new project. Workspace routing edits are preserved.');label.setWordWrap(True);box.addWidget(label)
            table=QTableWidget(len(report['changes']),3);table.setHorizontalHeaderLabels(['Adopt','Asset','Before → current SHA256']);table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch);table.setAccessibleName('Routing processing content changes')
            for row,item in enumerate(report['changes']):
                check=QTableWidgetItem();check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable);check.setCheckState(Qt.CheckState.Unchecked)
                if item['current_sha256'] is None or item['selector'].startswith('sources.') or item['selector']=='narration':check.setFlags(Qt.ItemFlag.NoItemFlags)
                table.setItem(row,0,check)
                for column,text in ((1,item['selector']),(2,item['previous_sha256']+' → '+(item['current_sha256'] or 'MISSING'))):
                    cell=QTableWidgetItem(text);cell.setFlags(cell.flags()&~Qt.ItemFlag.ItemIsEditable);cell.setToolTip(item['path']);table.setItem(row,column,cell)
            box.addWidget(table)
            def apply():
                updates={item['selector']:item['current_sha256'] for row,item in enumerate(report['changes']) if table.item(row,0).checkState()==Qt.CheckState.Checked}
                if not updates:label.setText('Choose at least one available processing change.');return
                dialog.accept()
                def adopted(result):
                    self.revision=result['project']['revision'];self.saved=result['project'];self.message('Reviewed routing processing updated. '+('Assets ready.' if result['ready'] else str(result['issues'])))
                self.owner.request('project.processing.adopt',{'project':str(self.path),'expected_revision':self.revision,'updates':updates},adopted)
            box.addWidget(action('Apply reviewed processing',apply));box.addWidget(action('Cancel review',dialog.reject));dialog.exec()
        self.owner.request('project.processing.review',{'project':str(self.path)},reviewed)
    def open(self):
        if self.owner.busy:self.message('Wait for the active operation before opening a different project.');return
        if not self.guard_unsaved(self.open):return
        path=QFileDialog.getOpenFileName(self,'Open routing project',filter='Arranger project (*.json)')[0]
        if not path:return
        from project import inspect
        try:
            report=inspect(Path(path));data=report['project']
            if data['schema']!=7:raise ValueError('Open score/sample projects in the main workspace.')
            self.graph=deepcopy(data['graph']);self.sources=deepcopy(data['graph_sources']);self.worker=data['worker'];self.score=data.get('score');self.path=Path(path);self.revision=data['revision'];self.saved=data
            self.expected_sources={};self.proposal_brief=None
            self.pending_forms={};self.pending_outputs=None;self.form_name=None;self.form_baseline=None;self.output_baseline=None
            self.history.clear()
            self.seconds.setValue(data['seconds']);self.tempo.setValue(data['tempo'] or 120);self.tail.setValue(data['tail_seconds']);self.refresh();self.message('Project reopened. '+('Assets ready.' if report['ready'] else str(report['issues'])))
        except (ValueError,OSError) as error:self.message(error)
    def save(self,after=None):
        if self.owner.busy:return
        if self.has_pending():self.message('Unapplied routing controls are preserved. Apply each edited inspector/automation/mixer/output panel, or restore its applied values, before saving or rendering.');return
        path=self.path or QFileDialog.getSaveFileName(self,'Save routing project',filter='Arranger project (*.json)')[0]
        if not path:return
        arguments={'project':str(path),'graph':self.graph,'sources':self.sources,'worker':self.worker,'seconds':self.seconds.value(),'tempo':self.tempo.value(),'tail_seconds':self.tail.value(),'expected_revision':self.revision}
        if self.score:arguments['score']=self.score
        if self.expected_sources:arguments['source_assets']={name:asset for name,asset in self.expected_sources.items() if name in self.sources and 'file' in self.sources[name]}
        if self.proposal_brief:arguments['brief']=self.proposal_brief
        if self.saved and self.saved.get('narration'):arguments.update(voice=self.saved['narration']['path'],voice_settings=self.saved['narration']['settings'])
        def saved(report):
            self.path=Path(path);self.saved=report['project'];self.revision=self.saved['revision'];self.message(f'Routing saved · revision{self.revision}. '+('Assets ready.' if report['ready'] else str(report['issues'])))
            self.expected_sources={};self.proposal_brief=None
            if callable(after):after()
        self.owner.request('project.graph.save',arguments,saved)
    def package(self):
        if self.owner.busy:self.message('Finish active work before packaging a project.');return
        if not self.path or self.has_changes():self.message('Save the routing project before packaging its exact revision.');return
        destination=QFileDialog.getSaveFileName(self,'New portable routing project folder (must not exist)')[0]
        if not destination:return
        self.owner.request('project.bundle.export',{'project':str(self.path),'destination':destination},lambda result:self.message(f"Portable routing project copied · {result['files']} audio/state assets. Plugins, worker and opaque libraries remain separate."))
    def choose_worker(self):
        if self.owner.busy:self.message('Finish active work before changing the host engine.');return
        from runtime import native_tool
        path=QFileDialog.getOpenFileName(self,'Choose local arranger-vst3 host engine',str(native_tool('arranger-vst3.exe').parent),'Host engine (arranger-vst3.exe)')[0]
        if not path:return
        self.worker=str(Path(path).resolve());self.message('Local host selected. Save pins this explicit selection; rendering still validates plugin/state compatibility. No engine was downloaded or installed.')
    def render(self):
        def submit():
            from assets import digest
            jobs=self.owner.result_jobs(reserve=True);jobs.mkdir(parents=True,exist_ok=True)
            def ready(result):
                self.owner.output=result['audio'];self.owner.output_measurements=result.get('measurements');self.owner.measurement_path=Path(result['audio']);self.message('MP3 ready. Use Play last result to audition the rendered graph.')
            self.owner.request('jobs.submit',{'project':str(self.path),'project_sha256':digest(self.path),'request_id':str(uuid.uuid4()),'jobs':str(jobs)},ready)
        self.save(submit)
