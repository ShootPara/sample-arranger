"""Accessible Qt workspace using the same local commands as automation clients."""
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid
import sqlite3
from copy import deepcopy
from PySide6.QtCore import Qt,QProcess,QProcessEnvironment,QRectF,QUrl,QTimer
from PySide6.QtGui import QAction,QColor,QFont,QPainter,QPen,QBrush,QKeySequence,QIcon,QDesktopServices
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,
    QSplitter,QLabel,QLineEdit,QPushButton,QComboBox,QDoubleSpinBox,QCheckBox,QFileDialog,
    QTableWidget,QTableWidgetItem,QHeaderView,QTabWidget,QGraphicsView,QGraphicsScene,
    QGraphicsRectItem,QAbstractItemView,QProgressBar,QSpinBox,QDialog,QDialogButtonBox,QScrollArea,QMessageBox,QInputDialog)
from brief import interpret
from music import compile_intent,validate as validate_score,note_identity,chord_label
from project import save as save_project,pinned_sections
from runtime import module_command,native_tool,resource

DATA=Path(os.environ["LOCALAPPDATA"],"SampleArranger")
STYLE="""
QMainWindow,QWidget {background:#111923;color:#e5edf4;font-family:'Segoe UI';font-size:12px;}
QLabel#brand {font-size:23px;font-weight:700;letter-spacing:2px;}
QLabel#subtle {color:#a9bacb;} QLabel#status {color:#79ddd0;padding:8px;}
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox {background:#1c2a39;border:1px solid #3a5064;border-radius:5px;padding:7px;selection-background-color:#286f76;}
QPushButton {background:#253a4b;border:1px solid #425c71;border-radius:5px;padding:8px 12px;}
QPushButton:hover {background:#34556a;} QPushButton:focus {border:2px solid #85e9dd;}
QPushButton:disabled {color:#8a9ba9;background:#1b2935;}
QPushButton#primary {background:#296d72;border:1px solid #6ad6cc;font-weight:600;}
QTableWidget {background:#172330;alternate-background-color:#1c2a39;gridline-color:#304354;border:1px solid #304354;selection-background-color:#28576c;}
QHeaderView::section {background:#233647;color:#dbe8f0;padding:7px;border:0px;border-bottom:1px solid #42566b;}
QTabWidget::pane {border:1px solid #304354;} QTabBar::tab {background:#223343;padding:9px 14px;}
QTabBar::tab:selected {background:#2d6972;color:white;}
QGraphicsView {border:1px solid #304354;background:#0c131c;border-radius:6px;}
QProgressBar {border:0px;background:#20303f;max-height:5px;} QProgressBar::chunk {background:#58ccbe;}
QSplitter::handle {background:#263a4b;width:2px;}
"""


def button(text,callback,primary=False):
    control=QPushButton(text);control.setAccessibleName(text)
    if primary:control.setObjectName("primary")
    control.clicked.connect(callback)
    return control


class Clip(QGraphicsRectItem):
    def __init__(self,owner,index,x,width,section):
        super().__init__(0,0,max(18,width),58 if owner.score else 94)
        self.owner,self.index,self.section=owner,index,section
        self.setPos(x,64);self.setBrush(QColor("#214e5c"));self.setPen(QPen(QColor("#61cbbf"),1))
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setToolTip(f"Section {index+1}: {section['sample']} · {section['seconds']:g}s. Drag right edge or edit the section table.")
        self.resizing=False
    def paint(self,painter,option,widget=None):
        super().paint(painter,option,widget)
        waveform=self.owner.waveforms.get(self.section["sample"])
        if waveform:
            peaks=waveform["peaks"];width=max(1,int(self.rect().width()-20));middle=self.rect().height()-17
            height=9 if self.owner.score else 16;rate=self.section.get("target_bpm",1)/(self.section["source_bpm"]*self.section["beat_scale"]) if "source_bpm" in self.section else 1
            painter.setPen(QPen(QColor("#54b7b2"),1))
            for x in range(width):
                second=(x/width*self.section["seconds"]*rate)%waveform["source_seconds"]
                if second>=waveform["preview_seconds"]:continue
                low,high=peaks[min(len(peaks)-1,int(second/waveform["preview_seconds"]*len(peaks)))]
                painter.drawLine(x+10,int(middle-max(-1,min(1,high))*height),x+10,int(middle-max(-1,min(1,low))*height))
        painter.setPen(QColor("#ecf8fa"))
        painter.drawText(self.rect().adjusted(10,12,-10,-10),Qt.TextFlag.TextWordWrap,
                         f"{self.index+1}  {self.section['sample']}\n{self.section['seconds']:g}s")
        painter.setPen(QPen(QColor("#8fe4da"),2));painter.drawLine(int(self.rect().width()-7),10,int(self.rect().width()-7),int(self.rect().height()-10))
    def mousePressEvent(self,event):
        self.owner.select_section(self.index);self.resizing=event.pos().x()>self.rect().width()-14
        self.start=event.scenePos().x();self.length=self.section["seconds"];super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.resizing:
            self.pending=max(0.1,self.length+(event.scenePos().x()-self.start)/self.owner.pixels_per_second)
            self.setRect(0,0,max(18,self.pending*self.owner.pixels_per_second),58 if self.owner.score else 94)
        else:super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        # Defer model refresh: rebuilding the scene during this callback deletes this item.
        if self.resizing:
            from PySide6.QtCore import QTimer
            index,length=self.index,getattr(self,"pending",self.length)
            QTimer.singleShot(0,lambda:self.owner.resize_section(index,length))
        self.resizing=False;super().mouseReleaseEvent(event)


class NoteClip(QGraphicsRectItem):
    def __init__(self,owner,index,note,x,y,width,color):
        super().__init__(0,0,max(4,width),4)
        self.owner,self.index,self.note=owner,index,note
        self.setPos(x,y);self.setBrush(QColor(color));self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setToolTip(f"{note['part']} · MIDI {note['pitch']} · tick {note['tick']} length {note['length']}. Drag to move; drag right edge to resize. Keyboard alternative: Notes table.")
        self.locked=note_identity(note) in owner.locked_note_signatures
        if self.locked:self.setPen(QPen(QColor('#f0d489'),1));self.setToolTip('LOCKED · '+self.toolTip()+' Unlock in the Notes controls before editing.')
    def mousePressEvent(self,event):
        self.start=event.scenePos();self.origin=self.pos();self.resizing=event.pos().x()>self.rect().width()-6
        self.owner.notes.selectRow(self.index);self.owner.editors.setCurrentWidget(self.owner.notes)
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.locked:event.ignore();return
        delta=event.scenePos()-self.start
        if self.resizing:self.setRect(0,0,max(4,self.note['length']*60/(self.owner.score['bpm']*960)*self.owner.pixels_per_second+delta.x()),4)
        else:self.setPos(self.origin+delta)
    def mouseReleaseEvent(self,event):
        from PySide6.QtCore import QTimer
        if self.locked:super().mouseReleaseEvent(event);return
        delta=event.scenePos()-self.start;pixels=self.owner.pixels_per_second
        ticks=delta.x()/pixels*self.owner.score['bpm']*960/60
        step=240 if self.owner.snap.isChecked() else 1;ticks=round(ticks/step)*step
        if self.resizing:changes=[{'action':'set','index':self.index,'field':'length','value':self.note['length']+ticks}]
        else:
            pitch_step=3 if self.owner.sections else 4
            changes=[{'action':'set','index':self.index,'field':'tick','value':self.note['tick']+ticks},
                     {'action':'set','index':self.index,'field':'pitch','value':self.note['pitch']-round(delta.y()/pitch_step)}]
        QTimer.singleShot(0,lambda:self.owner.apply_note_changes(changes,self.index));super().mouseReleaseEvent(event)


class HarmonyClip(QGraphicsRectItem):
    def __init__(self,owner,index,chord,x,y,width):
        super().__init__(0,0,max(1,width),15);self.owner,self.index=owner,index;self.label=chord_label(owner.score,chord)
        protections=[spec for spec in owner.score.get('musical_locks',[]) if spec['bar']==index]
        if protections:self.label+=' · protected'
        self.setPos(x,y);self.setBrush(QColor('#3d3b30'));self.setPen(QPen(QColor('#8f865d'),.5));self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setToolTip(f"Bar{index+1} · {self.label} · degree{chord['degree']} · MIDI voicing {chord['pitches']}. Select to edit the harmonic intention table."+(' Protected: '+', '.join(spec['kind']+' / '+spec['part'] for spec in protections) if protections else ''))
    def paint(self,painter,option,widget=None):
        super().paint(painter,option,widget)
        if self.rect().width()>=18:
            painter.setPen(QColor('#f0dfaa'));painter.setFont(QFont('Segoe UI',8));painter.drawText(self.rect().adjusted(3,0,-3,0),Qt.AlignmentFlag.AlignVCenter,self.label)
    def mousePressEvent(self,event):
        self.owner.harmony_table.selectRow(self.index);self.owner.editors.setCurrentWidget(self.owner.harmony_table);super().mousePressEvent(event)


class Workspace(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle("Sample Arranger · Workspace");self.resize(1440,900);self.setMinimumSize(1080,700)
        self.sections=[];self.score=None;self.samples=[];self.project_path=None;self.revision=0;self.source_assets={};self.voice_asset=None
        self.initial=None;self.output=None;self.busy=False;self.tasks=[];self.loading=False;self.pixels_per_second=18;self.active_operation=None
        self.plugin_inventory=[];self.parameters={};self.paths={};self.owned_snapshots=set();self.instruments={};self.waveforms={}
        self.expected_processing={};self.expected_instruments={}
        self.released_note_ids=set()
        self.released_musical_keys=set()
        self.saved_effect_class_id=None;self.parameter_class_id=None
        self.voice_report=None
        from plan_history import PlanHistory
        self.history=PlanHistory()
        self.command_guards={};self.cancel_deadlines=set();self.closing=False
        self.forced_cancellations=set()
        self.temporary_session=None
        self.output_measurements=None;self.measurement_path=None
        DATA.mkdir(parents=True,exist_ok=True);self.settings=DATA/"workspace-settings.json"
        try:self.saved=json.loads(self.settings.read_text(encoding="utf-8"))
        except (OSError,ValueError):self.saved={}
        root=QWidget();self.setCentralWidget(root);layout=QVBoxLayout(root);layout.setContentsMargins(20,16,20,12)
        header=QHBoxLayout();brand=QLabel("SAMPLE / ARRANGER");brand.setObjectName("brand");header.addWidget(brand);header.addStretch()
        badge=QLabel("LOCAL AUDIO  ·  MP3 192K  ·  ≤ 4 MIN");badge.setObjectName("subtle");header.addWidget(badge);layout.addLayout(header)
        self.split=QSplitter(Qt.Orientation.Horizontal);layout.addWidget(self.split,1)
        self.build_library();self.build_center();self.build_inspector();self.split.setSizes([280,760,340])
        if not self.paths['worker'].text() and native_tool('arranger-vst3.exe').is_file():self.paths['worker'].setText(str(native_tool('arranger-vst3.exe')))
        self.progress=QProgressBar();self.progress.setRange(0,1);self.progress.setValue(0);layout.addWidget(self.progress)
        transport=QHBoxLayout();transport.addWidget(button("Play result",self.preview));transport.addWidget(button("Stop preview",self.stop_preview));transport.addWidget(button('Output levels',self.show_output_levels));transport.addWidget(button('Routing workspace…',self.open_routing))
        self.state=QLabel("Open a project or choose a library. No app cloud uploads.");self.state.setObjectName("status");self.state.setTextFormat(Qt.TextFormat.PlainText);self.state.setWordWrap(True);transport.addWidget(self.state,1)
        self.cancel_button=button("Cancel job",self.cancel);self.cancel_button.setEnabled(False);transport.addWidget(self.cancel_button)
        self.render_button=button("Render MP3",self.render_job,True);transport.addWidget(self.render_button);layout.addLayout(transport)
        self.preview_process=QProcess(self)
        for label,key,callback in (("Open project",QKeySequence.StandardKey.Open,self.open_project),("Save project",QKeySequence.StandardKey.Save,self.save_project),
                                   ("Render",QKeySequence("Ctrl+Return"),self.render_job),("Cancel",QKeySequence("Escape"),self.cancel),
                                   ("Undo plan edit",QKeySequence.StandardKey.Undo,lambda:self.undo_plan(False)),("Redo plan edit",QKeySequence.StandardKey.Redo,lambda:self.undo_plan(True))):
            action=QAction(label,self);action.setShortcut(key);action.triggered.connect(callback);self.addAction(action)
        self.draw_timeline()
        self.paths['plugin'].textChanged.connect(lambda:self.restore_effect_selection(None,{}))
        from workspace_recovery import Drafts
        self.drafts=Drafts(DATA/'workspace-recovery');self.recovery_baseline=self.recovery_signature();self.last_draft_signature=None
        self.draft_timer=QTimer(self);self.draft_timer.setInterval(2000);self.draft_timer.timeout.connect(self.persist_draft);self.draft_timer.start()
        if self.drafts.available():self.recovery_notice.setText('An earlier workspace draft is available. Restore it explicitly to review unsaved edits.')

    def path_field(self,form,key,label,folder=False):
        row=QHBoxLayout();edit=QLineEdit(self.saved.get(key,""));edit.setAccessibleName(label);edit.setPlaceholderText(label);self.paths[key]=edit
        def choose():
            value=QFileDialog.getExistingDirectory(self,label,edit.text()) if folder else QFileDialog.getOpenFileName(self,label,edit.text())[0]
            if value:edit.setText(value)
        row.addWidget(edit,1);row.addWidget(button("Choose…",choose));form.addRow(label,row);return edit

    def build_library(self):
        panel=QWidget();box=QVBoxLayout(panel);box.setContentsMargins(0,12,12,0)
        title=QLabel("LIBRARY");title.setFont(QFont("Segoe UI",13,QFont.Weight.Bold));box.addWidget(title)
        self.search=QLineEdit();self.search.setPlaceholderText("Search samples…");self.search.setAccessibleName("Search sample library");self.search.returnPressed.connect(self.search_library);box.addWidget(self.search)
        controls=QHBoxLayout();controls.addWidget(button("Search",self.search_library));controls.addWidget(button("Add folder",self.scan_folder));box.addLayout(controls)
        box.addWidget(button('Recommend at project tempo',self.recommend_samples))
        box.addWidget(button('Build layered sample plan…',self.plan_ensemble))
        self.library=QTableWidget(0,2);self.library.setHorizontalHeaderLabels(["Sample","Tempo"]);self.library.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.library.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.library.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.library.setAccessibleName("Available samples")
        self.library.itemSelectionChanged.connect(self.selected_sample);self.library.itemDoubleClicked.connect(lambda _:self.add_sample());box.addWidget(self.library,1)
        row=QHBoxLayout();row.addWidget(button("Audition",self.audition));row.addWidget(button("Add to plan",self.add_sample));box.addLayout(row)
        box.addWidget(button("Preview waveform",self.preview_waveform))
        box.addWidget(button("Read embedded metadata",self.read_metadata))
        self.waveform_scene=QGraphicsScene(self);self.waveform_view=QGraphicsView(self.waveform_scene);self.waveform_view.setFixedHeight(72);self.waveform_view.setAccessibleName("Selected sample waveform preview, first thirty seconds maximum");self.waveform_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.waveform_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);box.addWidget(self.waveform_view)
        self.waveform_caption=QLabel("Select a sample, then preview its waveform.");self.waveform_caption.setWordWrap(True);self.waveform_caption.setObjectName("subtle");box.addWidget(self.waveform_caption);self.display_waveform()
        self.observation=QLabel("Select a sample to inspect tempo evidence.");self.observation.setWordWrap(True);box.addWidget(self.observation)
        row=QHBoxLayout();self.corrected=QDoubleSpinBox();self.corrected.setRange(20,400);self.corrected.setValue(120);self.corrected.setAccessibleName("Corrected sample BPM")
        row.addWidget(self.corrected);row.addWidget(button("Set BPM",self.correct_tempo));row.addWidget(button("Analyze",self.measure_tempo));box.addLayout(row)
        identity_row=QHBoxLayout();identity_row.addWidget(button('Hash audio',self.hash_sample));identity_row.addWidget(button('Relocate entry…',self.relocate_catalog_sample));box.addLayout(identity_row)
        box.addWidget(button('Correct musical role / key…',self.correct_musical_tags));self.split.addWidget(panel)

    def build_center(self):
        panel=QWidget();box=QVBoxLayout(panel);box.setContentsMargins(6,12,6,0)
        title=QLabel("ARRANGEMENT");title.setFont(QFont("Segoe UI",13,QFont.Weight.Bold));box.addWidget(title)
        self.brief=QLineEdit();self.brief.setAccessibleName("Music brief");self.brief.setPlaceholderText("A one minute upbeat music bed…");box.addWidget(self.brief)
        row=QHBoxLayout();self.mode=QComboBox();self.mode.addItems(["Sample library","Built-in instruments"]);self.mode.setAccessibleName("Planning source")
        row.addWidget(self.mode);row.addWidget(button("Build plan",self.plan));row.addWidget(button('AI plan',self.ai_plan));row.addWidget(button("New brief",self.new_brief));row.addStretch()
        self.snap=QCheckBox("Snap to ¼ beat");self.snap.setChecked(True);row.addWidget(self.snap);box.addLayout(row)
        history_row=QHBoxLayout();history_row.addWidget(button('Undo edit',lambda:self.undo_plan(False)));history_row.addWidget(button('Redo edit',lambda:self.undo_plan(True)));history_row.addWidget(button('Lock / unlock selected note',self.toggle_note_lock));history_row.addWidget(button('Melody rhythm…',self.edit_melody_rhythm));history_row.addStretch();box.addLayout(history_row)
        from broker_port import status
        hint_row=QHBoxLayout();self.ai_hint=QLabel('Local rules available · AI '+('configured' if status()['configured'] else 'not configured'));self.ai_hint.setObjectName('subtle');self.ai_hint.setWordWrap(True);hint_row.addWidget(self.ai_hint);hint_row.addStretch();hint_row.addWidget(button('AI connection…',self.ai_connection));hint_row.addWidget(button('Protect music…',self.edit_musical_locks));box.addLayout(hint_row)
        self.scene=QGraphicsScene(self);self.timeline=QGraphicsView(self.scene);self.timeline.setAccessibleName("Arrangement timeline; use section and note tables for keyboard editing")
        self.timeline.setRenderHint(QPainter.RenderHint.Antialiasing);self.timeline.setMinimumHeight(240);box.addWidget(self.timeline,2)
        self.timeline.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)
        self.editors=QTabWidget();box.addWidget(self.editors,1);section_panel=QWidget();section_box=QVBoxLayout(section_panel)
        self.section_table=QTableWidget(0,2);self.section_table.setHorizontalHeaderLabels(["Sample","Seconds"]);self.section_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.section_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.section_table.setAccessibleName("Editable arrangement sections");self.section_table.itemChanged.connect(self.section_edited);section_box.addWidget(self.section_table)
        row=QHBoxLayout()
        for text,action in (("Earlier",lambda:self.move_section(-1)),("Later",lambda:self.move_section(1)),("Remove",self.remove_section),("Tempo…",self.match_tempo),("Fit timeline",self.fit_timeline)):row.addWidget(button(text,action))
        row.addStretch();section_box.addLayout(row);self.editors.addTab(section_panel,"Sections")
        self.notes=QTableWidget(0,5);self.notes.setHorizontalHeaderLabels(["Part","Tick","Length","Pitch","Velocity"]);self.notes.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.notes.setAccessibleName("Editable note intentions realized as exact tick events");self.notes.itemChanged.connect(self.note_edited);self.editors.addTab(self.notes,"Notes")
        self.harmony_table=QTableWidget(0,4);self.harmony_table.setHorizontalHeaderLabels(['Bar','Degree1–7','Chord','MIDI voicing']);self.harmony_table.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeMode.Stretch)
        self.harmony_table.setAccessibleName('Editable harmonic intentions; change a diatonic degree to revoice the selected bar');self.harmony_table.itemChanged.connect(self.harmony_edited);self.editors.addTab(self.harmony_table,'Harmony');self.split.addWidget(panel)

    def build_inspector(self):
        panel=QWidget();box=QVBoxLayout(panel);box.setContentsMargins(12,12,0,0)
        title=QLabel("INSPECTOR");title.setFont(QFont("Segoe UI",13,QFont.Weight.Bold));box.addWidget(title);self.inspector=QTabWidget();box.addWidget(self.inspector,1)
        project=QWidget();form=QFormLayout(project);self.path_field(form,"catalog","Catalog")
        jobs=self.path_field(form,"jobs","Job folders",True)
        if not jobs.text():jobs.setText(str(DATA/"jobs"))
        self.temporary_results=QCheckBox('Temporary result session');self.temporary_results.setAccessibleName('Temporary normal results cleared on workspace close')
        self.temporary_results.setToolTip('Normal MP3 results and their receipts stay in an owned temporary session until this workspace closes. Catalog and explicitly saved projects remain independent. Continuous mode always has its own no-save policy.')
        form.addRow(self.temporary_results)
        form.addRow(button('Clear temporary results…',self.clear_temporary_results))
        self.path_field(form,"voice","Narration");self.bpm=QDoubleSpinBox();self.bpm.setRange(40,240);self.bpm.setDecimals(2);self.bpm.setSingleStep(0.1);self.bpm.setValue(128);self.bpm.setAccessibleName("Project tempo");form.addRow("Tempo",self.bpm)
        self.key=QComboBox();self.key.addItems(["C","C♯","D","D♯","E","F","F♯","G","G♯","A","A♯","B"]);self.key.setAccessibleName("Tonic");form.addRow("Tonic",self.key)
        self.scale=QComboBox();self.scale.addItems(["major","minor"]);self.scale.setAccessibleName("Mode");form.addRow("Mode",self.scale)
        self.voice_offset=QDoubleSpinBox();self.voice_offset.setRange(0,240);self.voice_offset.setDecimals(3);self.voice_offset.setSuffix(' s');self.voice_offset.setAccessibleName('Narration placement in seconds');form.addRow('Voice start',self.voice_offset)
        self.voice_gain=QDoubleSpinBox();self.voice_gain.setRange(-24,12);self.voice_gain.setDecimals(1);self.voice_gain.setSuffix(' dB');self.voice_gain.setAccessibleName('Narration gain');form.addRow('Voice level',self.voice_gain)
        self.music_gain=QDoubleSpinBox();self.music_gain.setRange(-60,0);self.music_gain.setDecimals(1);self.music_gain.setValue(-5.2);self.music_gain.setSuffix(' dB');self.music_gain.setAccessibleName('Music level under narration');form.addRow('Music level',self.music_gain)
        self.ducking=QCheckBox('Automatically duck music under voice');self.ducking.setChecked(True);form.addRow(self.ducking)
        form.addRow(button('Check voice placement',self.check_voice))
        self.paths['voice'].textChanged.connect(self.draw_timeline);self.voice_offset.valueChanged.connect(self.draw_timeline)
        row=QHBoxLayout();row.addWidget(button("Open project",self.open_project));row.addWidget(button("Save project",self.save_project));form.addRow(row);self.inspector.addTab(self.scroll_panel(project),"Project")
        self.keep_recovery=QCheckBox('Keep local recovery drafts');self.keep_recovery.setChecked(self.saved.get('keep_recovery',True));self.keep_recovery.setAccessibleName('Keep editable project recovery locally; no audio')
        self.keep_recovery.setToolTip('Stores brief, note/clip edits, local paths and content pins in local app data. No audio or plugin binaries. Disabled for temporary results and while continuous mode runs. Existing earlier drafts are retained until you manage them.')
        form.addRow(self.keep_recovery)
        self.recovery_notice=QLabel('Editable drafts stay on this PC; saved projects remain separate.');self.recovery_notice.setWordWrap(True);form.addRow(self.recovery_notice)
        form.addRow(button('Restore workspace draft…',self.restore_draft))
        form.addRow(button('Package saved project…',self.package_project));form.addRow(button('Open portable project…',self.import_project_package))
        form.addRow(button("Relink selected sample…",self.relink_sample))
        form.addRow(button("Review processing updates…",self.review_processing))
        plugins=QWidget();form=QFormLayout(plugins);worker=self.path_field(form,"worker","Host engine")
        installed=native_tool('arranger-vst3.exe')
        if not worker.text() and installed.is_file():worker.setText(str(installed))
        self.path_field(form,"plugin","Master effect");self.path_field(form,"state","Preset state")
        help=QLabel('The master effect processes the complete mix, including narration.');help.setWordWrap(True);form.addRow(help);form.addRow(button("Inspect plugin",self.inspect_plugin))
        form.addRow(button('Plugin library…',self.plugin_library))
        self.classes=QComboBox();self.classes.setAccessibleName("Plugin component class");self.classes.currentIndexChanged.connect(self.show_parameters);form.addRow("Component",self.classes)
        self.parameter_table=QTableWidget(0,2);self.parameter_table.setHorizontalHeaderLabels(["Parameter","0–1 value"]);self.parameter_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.parameter_table.setAccessibleName("Exposed plugin parameters");self.parameter_table.itemChanged.connect(self.parameter_edited);form.addRow(self.parameter_table);form.addRow(button("Open native editor",self.open_native))
        form.addRow(button("Save parameter state",lambda:self.open_native(False)))
        form.addRow(button('Displayed values / programs…',self.effect_parameter_dialog))
        row=QHBoxLayout();row.addWidget(button("Import preset",lambda:self.preset_file(False,False)));row.addWidget(button("Export preset",lambda:self.preset_file(False,True)));form.addRow(row);self.inspector.addTab(self.scroll_panel(plugins),"Plugins")
        instruments=QWidget();form=QFormLayout(instruments)
        help=QLabel("Assign a Windows VST3 instrument to a composed part. Unassigned parts use built-in sounds. Routing and saved state stay with the project.");help.setWordWrap(True);form.addRow(help)
        self.instrument_table=QTableWidget(0,2);self.instrument_table.setHorizontalHeaderLabels(["Part","Instrument"])
        self.instrument_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.instrument_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.instrument_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.instrument_table.setAccessibleName("Instrument assignments")
        form.addRow(self.instrument_table);form.addRow(button("Assign VST3 instrument…",self.assign_instrument))
        form.addRow(button("Use built-in sound",self.clear_instrument));form.addRow(button("Open instrument editor",self.edit_instrument))
        form.addRow(button("Instrument parameters…",self.instrument_parameters))
        row=QHBoxLayout();row.addWidget(button("Import preset",lambda:self.preset_file(True,False)));row.addWidget(button("Export preset",lambda:self.preset_file(True,True)));form.addRow(row)
        self.inspector.addTab(self.scroll_panel(instruments),"Instruments");self.refresh_instruments()
        continuous=QWidget();form=QFormLayout(continuous)
        explanation=QLabel("TEMPORARY PLAYBACK\n\nMusic evolves in roughly one-minute chunks. Heard audio is discarded; there is no recording or export. Stop at any time.")
        explanation.setWordWrap(True);form.addRow(explanation)
        self.continuous_source=QComboBox();self.continuous_source.addItems(["Built-in music","Selected library sample"]);self.continuous_source.setAccessibleName("Continuous source");form.addRow("Source",self.continuous_source)
        self.continuous_effect=QCheckBox("Use current effect and preset");form.addRow(self.continuous_effect)
        self.continuous_effect_bus=QSpinBox();self.continuous_effect_bus.setRange(0,7);self.continuous_effect_bus.setAccessibleName('Continuous effect selected output bus');self.continuous_effect_bus.setToolTip('Only this output is played; other plugin outputs are discarded in memory. Simultaneous output mixing uses the offline routing workspace.');form.addRow('Effect output bus',self.continuous_effect_bus)
        self.continuous_effect_bus.setEnabled(False);self.continuous_effect.toggled.connect(self.continuous_effect_bus.setEnabled)
        form.addRow(button("Start disposable playback",self.start_continuous,True));form.addRow(button("Stop playback",self.cancel))
        self.continuous_health=QLabel("Not playing. At most two future chunks are queued.");self.continuous_health.setWordWrap(True);form.addRow(self.continuous_health)
        self.inspector.addTab(self.scroll_panel(continuous),"Continuous")
        jobs_panel=QWidget();form=QVBoxLayout(jobs_panel)
        label=QLabel('Normal results stay in your job folders until you delete them. Continuous audio never appears here.');label.setWordWrap(True);form.addWidget(label)
        self.retained_jobs=[];self.jobs_table=QTableWidget(0,2);self.jobs_table.setHorizontalHeaderLabels(['Created / updated','Duration'])
        self.jobs_table.setAccessibleName('Retained music jobs');self.jobs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.jobs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.jobs_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);form.addWidget(self.jobs_table)
        form.addWidget(button('Refresh saved results',self.refresh_jobs));form.addWidget(button('Play selected result',self.play_retained_job))
        form.addWidget(button('Open result folder',self.open_job_folder));form.addWidget(button('Delete selected result…',self.delete_retained_job))
        self.inspector.addTab(self.scroll_panel(jobs_panel),'Results')
        self.temporary_results.toggled.connect(lambda checked:(self.retained_jobs.clear(),self.jobs_table.setRowCount(0),self.message('Temporary normal results will clear on Close; catalog and saved projects remain.' if checked else 'Normal results will remain in your selected job folders.')))
        info=QLabel("Normal jobs retain results and provenance in your folders. Continuous playback is disposable and has no save route.");info.setWordWrap(True);info.setObjectName("subtle");box.addWidget(info);self.split.addWidget(panel)

    def message(self,text):self.state.setText(str(text)[:2000])
    def recovery_state(self):
        return {**deepcopy(self.plan_state()),'voice_asset':deepcopy(self.voice_asset),'paths':{key:edit.text() for key,edit in self.paths.items()},
                'project_path':self.project_path,'revision':self.revision,'brief':self.brief.text(),'initial':self.initial,
                'parameters':deepcopy(self.parameters),'instruments':deepcopy(self.instruments),'expected_processing':deepcopy(self.expected_processing),
                'expected_instruments':deepcopy(self.expected_instruments),'released_note_ids':[list(v) for v in sorted(self.released_note_ids)],
                'released_musical_keys':[list(v) for v in sorted(self.released_musical_keys)],
                'voice_settings':self.voice_options(),'bpm':self.bpm.value(),'root':self.key.currentIndex(),'mode':self.scale.currentText(),
                'planning_source':self.mode.currentIndex(),'class_id':self.processing().get('class_id')}
    def recovery_signature(self):
        from workspace_recovery import encode
        return encode(self.recovery_state())
    def mark_workspace_saved(self):
        self.recovery_baseline=self.recovery_signature();self.last_draft_signature=None;self.drafts.clear_owned();self.recovery_notice.setText('All editable changes are saved.' if self.project_path else 'No unsaved editable changes.')
    def persist_draft(self):
        if not hasattr(self,'drafts'):return
        try:
            if not self.keep_recovery.isChecked() or self.temporary_results.isChecked():
                self.drafts.clear_owned();self.last_draft_signature=None;self.recovery_notice.setText('Editable recovery is off for this workspace.');return
            if self.busy:return
            signature=self.recovery_signature()
            if signature==self.recovery_baseline:
                self.drafts.clear_owned();self.last_draft_signature=None;self.recovery_notice.setText('All editable changes are saved.' if self.project_path else 'No unsaved editable changes.');return
            if signature==self.last_draft_signature:return
            self.drafts.write(self.recovery_state());self.last_draft_signature=signature
            self.recovery_notice.setText('Unsaved edits have a local recovery draft. No audio is included.')
        except (OSError,ValueError,TypeError) as error:self.recovery_notice.setText('Recovery draft could not be updated: '+str(error))
    def confirm_workspace_replacement(self):
        if self.recovery_signature()==self.recovery_baseline:return True
        question=QMessageBox(self);question.setWindowTitle('Preserve unsaved workspace edits');question.setText('Save the current project or keep a local recovery draft before opening another?')
        save=question.addButton('Save project',QMessageBox.ButtonRole.AcceptRole)
        keep=question.addButton('Keep recovery draft',QMessageBox.ButtonRole.ActionRole)
        question.addButton(QMessageBox.StandardButton.Cancel);question.exec()
        if question.clickedButton()==save:return bool(self.save_project())
        if question.clickedButton()==keep:
            if not self.keep_recovery.isChecked() or self.temporary_results.isChecked():self.message('Local recovery is disabled for this workspace. Save explicitly or cancel opening.');return False
            try:
                self.drafts.write(self.recovery_state())
                # Rotate ownership so subsequent edits cannot replace the draft
                # intentionally retained for the previous workspace.
                from workspace_recovery import Drafts
                self.drafts=Drafts(self.drafts.root);self.last_draft_signature=None;return True
            except (OSError,ValueError) as error:self.message('Could not preserve current edits: '+str(error))
        return False
    def restore_draft(self):
        if self.busy:self.message('Finish or stop active work before restoring a draft.');return
        path=QFileDialog.getOpenFileName(self,'Restore local editable workspace draft',str(self.drafts.root),'Workspace drafts (draft-*.json)')[0]
        if not path:return
        try:
            state=self.drafts.read(path)
            if not self.confirm_workspace_replacement():return
            self.apply_recovery_state(state)
            self.persist_draft();self.message('Draft restored for review. Missing/changed assets and revision conflicts still block Save/render. Earlier draft files are retained.')
        except (OSError,ValueError,TypeError) as error:self.message('Draft was not restored: '+str(error))
    def apply_recovery_state(self,state):
        from workspace_recovery import validate
        state=deepcopy(validate(state))
        for key in ('sections','score','source_assets','voice_asset','project_path','revision','initial','instruments','expected_processing','expected_instruments'):setattr(self,key,state[key])
        for key,edit in self.paths.items():edit.setText(state['paths'].get(key,''))
        self.restore_effect_selection(state['class_id'],state['parameters']);self.released_note_ids={tuple(v) for v in state['released_note_ids']};self.released_musical_keys={tuple(v) for v in state.get('released_musical_keys',[])}
        self.brief.setText(state['brief']);self.bpm.setValue(state['bpm']);self.key.setCurrentIndex(state['root']);self.scale.setCurrentText(state['mode']);self.mode.setCurrentIndex(state['planning_source'])
        options=state['voice_settings'];self.voice_offset.setValue(options['offset_seconds']);self.voice_gain.setValue(options['voice_gain_db']);self.music_gain.setValue(options['music_gain_db']);self.ducking.setChecked(options['ducking'])
        self.output=None;self.voice_report=None;self.history.clear();self.refresh_instruments();self.refresh_plan()
    def scroll_panel(self,panel):
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);scroll.setWidget(panel)
        return scroll
    def selected_job(self):
        row=self.jobs_table.currentRow()
        return self.retained_jobs[row] if 0<=row<len(self.retained_jobs) else None
    def result_jobs(self,reserve=False):
        if self.temporary_results.isChecked():
            if self.temporary_session is None:
                from temporary_jobs import TemporaryJobs
                self.temporary_session=TemporaryJobs()
            return self.temporary_session.reserve() if reserve else self.temporary_session.jobs
        return Path(self.paths['jobs'].text())
    def clear_temporary_results(self):
        if self.busy:self.message('Wait for owned work to stop before clearing temporary results.');return
        if self.temporary_session is None:self.message('No temporary normal-result session is open.');return
        if QMessageBox.question(self,'Clear temporary normal results?','Clear every normal result and receipt in this temporary session? Catalog, source audio, saved projects and normal retained job folders are preserved.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        self.stop_preview()
        try:
            session=self.temporary_session;session.close()
            if self.output and Path(self.output).is_relative_to(session.jobs):self.output=None
            self.temporary_session=None;self.retained_jobs.clear();self.jobs_table.setRowCount(0);self.message('Temporary normal results cleared. The next temporary render starts a fresh session.')
        except (OSError,ValueError) as error:self.message('Temporary result cleanup incomplete: '+str(error))
    def refresh_jobs(self):
        def listed(result):
            from datetime import datetime
            self.retained_jobs=result['jobs'];self.jobs_table.setRowCount(len(self.retained_jobs))
            for row,job in enumerate(self.retained_jobs):
                for column,text in enumerate((datetime.fromtimestamp(job['modified_ns']/1e9).strftime('%b %d · %H:%M:%S'),f"{job['seconds']:g}s" if type(job['seconds']) in (int,float) else 'Unknown')):
                    item=QTableWidgetItem(text);item.setToolTip(job['job_id']);self.jobs_table.setItem(row,column,item)
            self.message(f"{len(self.retained_jobs)} retained results shown."+(' Folder scan reached its safety limit.' if result['scan_limited'] else ''))
        try:jobs=self.result_jobs()
        except (OSError,ValueError) as error:self.message(str(error));return
        self.request('jobs.list',{'jobs':str(jobs),'limit':50},listed)
    def play_retained_job(self):
        job=self.selected_job()
        if job:self.play_file(str(Path(job['folder'])/'result.mp3'),240)
        else:self.message('Select a saved result first.')
    def open_job_folder(self):
        job=self.selected_job()
        if job:QDesktopServices.openUrl(QUrl.fromLocalFile(job['folder']))
        else:self.message('Select a saved result first.')
    def delete_retained_job(self):
        if self.busy:self.message('Wait for the active operation before deleting a result.');return
        job=self.selected_job()
        if not job:self.message('Select a saved result first.');return
        if not job['managed']:self.message('This older result has no complete ownership inventory. Review and remove its folder manually.');return
        dialog=QMessageBox(self);dialog.setWindowTitle('Delete saved result?');dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText('Delete this result, its saved processing states and provenance? Original samples, plugins, narration and project files are preserved.')
        dialog.setInformativeText(job['job_id']);dialog.setStandardButtons(QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No);dialog.setDefaultButton(QMessageBox.StandardButton.No)
        forget=QCheckBox('Also forget the duplicate-request receipt');dialog.setCheckBox(forget)
        if dialog.exec()!=QMessageBox.StandardButton.Yes:return
        self.stop_preview()
        def deleted(result):
            if self.output and Path(self.output).parent==Path(job['folder']):self.output=None
            self.refresh_jobs()
        self.request('jobs.delete',{'jobs':str(Path(job['folder']).parent),'job_id':job['job_id'],'expected_manifest_sha256':job['manifest_sha256'],'forget_receipt':forget.isChecked()},deleted)

    def request(self,operation,arguments,callback=None):
        if self.busy:self.message("A job is already running. Cancel it or wait.");return
        path=None
        try:
            payload=json.dumps({'contract':1,'operation':operation,'arguments':arguments},ensure_ascii=False,allow_nan=False).encode('utf-8')
            if len(payload)>256000:raise ValueError('Request exceeds the shared256000-byte command cap.')
            descriptor,path=tempfile.mkstemp(prefix="arranger-qt-request-",suffix=".json")
            with os.fdopen(descriptor,'wb') as output:output.write(payload)
        except (OSError,ValueError,TypeError) as error:
            if path:Path(path).unlink(missing_ok=True)
            self.message(str(error));return
        self.temporary_results.setEnabled(False)
        marker=Path(tempfile.gettempdir())/f"arranger-cancel-{uuid.uuid4()}";process=QProcess(self)
        environment=QProcessEnvironment.systemEnvironment();environment.insert("ARRANGER_CANCEL_FILE",str(marker));environment.insert("ARRANGER_OWNER_PID",str(os.getpid()));process.setProcessEnvironment(environment)
        self.busy=True;self.active_operation=operation;self.render_button.setEnabled(False);self.cancel_button.setEnabled(True);self.progress.setRange(0,0)
        self.tasks.append((process,marker,Path(path)));self.message(f"Working · {operation.replace('.', ' / ')}")
        diagnostic=bytearray();pending=bytearray()
        def read_diagnostic():
            data=bytes(process.readAllStandardError());diagnostic.extend(data);del diagnostic[:-16000]
            pending.extend(data)
            while b"\n" in pending:
                line,_,remaining=pending.partition(b"\n");pending[:]=remaining
                if line.startswith(b'command_ready ') and process not in self.command_guards:
                    try:
                        from command_guard import ProcessGuard
                        _,pid,creation=line.split();self.command_guards[process]=ProcessGuard(int(pid),int(creation))
                    except (ValueError,OSError):self.message('Command lifetime could not be verified. Cooperative cancellation remains available.')
                elif operation=="continuous.play":
                    try:
                        health=json.loads(line).get("continuous",{})
                        if health:self.continuous_health.setText(f"Playing · {health['frames_acknowledged']/44100:.1f}s acknowledged by the output API\n{health.get('queued_chunks',0)} future chunks queued\nAudio is discarded as playback advances.")
                    except (ValueError,KeyError,TypeError):pass
                elif line.startswith(b"child_started") and operation.endswith("render"):self.message("Rendering audio…")
                else:
                    try:
                        stage=json.loads(line).get('event',{}).get('stage')
                        labels={'validating':'Checking project assets…','rendering_audio':'Rendering music and narration…','measuring_output':'Checking output sound and duration…','publishing':'Finishing the job folder…','validating_graph':'Checking signal routes…','preparing_sources':'Preparing selected sources…','processing_graph':'Processing plugins and routing…'}
                        if stage in labels:self.message(labels[stage])
                    except (ValueError,TypeError):pass
            if len(pending)>16000:del pending[:-16000]
        process.readyReadStandardError.connect(read_diagnostic)
        def finished(code,status):
            if not any(task[0] is process for task in self.tasks):return
            read_diagnostic();stdout=bytes(process.readAllStandardOutput()).decode("utf-8","replace");stderr=diagnostic.decode("utf-8","replace")
            canceled=marker.exists();marker.unlink(missing_ok=True);Path(path).unlink(missing_ok=True)
            forced=process in self.forced_cancellations;self.forced_cancellations.discard(process)
            self.busy=False;self.active_operation=None;self.render_button.setEnabled(True);self.cancel_button.setEnabled(False);self.temporary_results.setEnabled(True);self.progress.setRange(0,1);self.progress.setValue(0)
            self.tasks[:]=[task for task in self.tasks if task[0] is not process]
            guard=self.command_guards.pop(process,None)
            if guard:guard.close()
            self.cancel_deadlines.discard(process)
            try:
                if canceled:
                    if operation=='continuous.play' and forced:
                        self.message('Stopped. Checking interrupted disposable audio cleanup…')
                        def cleaned(result):
                            self.message('Stopped. Owned inactive temporary audio cleared.' if not result['inactive_audio_bytes'] and not result['scan_limited'] and not result['unverified_owned_sessions'] else 'Stopped. Temporary audio cleanup is incomplete; review diagnostics before restarting.')
                        self.request('continuous.cleanup',{},cleaned)
                    else:self.message("Continuous playback stopped. Temporary audio cleared." if operation=="continuous.play" else "Canceled. Review the job folder if completion raced cancellation.")
                else:
                    if not stdout.strip():raise ValueError(stderr or process.errorString() or "The command returned no result.")
                    payload=json.loads(stdout)
                    if code:raise ValueError(payload.get("error",{}).get("message",stderr or "The operation failed."))
                    if callback:callback(payload["result"])
                    else:self.message("Done.")
            except (ValueError,KeyError,TypeError,OSError,sqlite3.Error) as error:self.message(str(error))
            for snapshot in self.owned_snapshots:snapshot.unlink(missing_ok=True)
            self.owned_snapshots.clear()
            process.deleteLater()
            if self.closing and not self.tasks:QTimer.singleShot(0,self.close)
        process.finished.connect(finished)
        process.errorOccurred.connect(lambda error:finished(-1,QProcess.ExitStatus.CrashExit) if error==QProcess.ProcessError.FailedToStart else None)
        command=module_command('commands','--request',path,'--events');process.start(command[0],command[1:])

    def new_brief(self):self.initial=None;self.message("New brief. Refinement replaces the earlier request.")
    def plan_ensemble(self):
        if self.busy:self.message('Finish active work before proposing a layered plan.');return
        intent=interpret(self.initial or self.brief.text(),self.brief.text() if self.initial is not None else None)
        if intent['state']!='ready':
            if intent['state']=='needs_input' and self.initial is None:self.initial=self.brief.text()
            self.message(intent['message']);return
        musical=intent['musical'];tempo=musical.get('bpm') or intent.get('recommended_bpm') or self.bpm.value()
        roles=['drum','bass' if intent['role']=='bass' else 'chords'];roles=[role for role in roles if role not in intent['excluded_roles']]
        if not roles:self.message('The requested exclusions leave no ensemble roles. Revise the brief or select sources manually.');return
        role_terms={'chords':intent['role']} if intent['role'] in ('piano','guitar','pad') else {}
        requested_state=self.recovery_signature()
        def proposed(result):
            if self.recovery_signature()!=requested_state:self.message('Workspace or brief changed while planning. Build a new layered plan to use the current request.');return
            from routing_workspace import RoutingWorkspace
            dialog=RoutingWorkspace(self,proposal=result);dialog.message('Review proposed layers. '+' '.join(result['warnings']));dialog.exec()
        self.request('arrangement.ensemble',{'catalog':self.paths['catalog'].text(),'seconds':intent['seconds'],'bpm':tempo,
                     'root':musical.get('root',self.key.currentIndex()),'mode':musical.get('mode',self.scale.currentText()),
                     'roles':roles,'role_terms':role_terms,'excluded_roles':intent['excluded_roles']},proposed)
    def plan_state(self):return {'sections':self.sections,'score':self.score,'source_assets':self.source_assets}
    def musical_releases(self,path):
        if not Path(path).is_file() or not self.released_musical_keys:return []
        from project import read
        from musical_locks import key
        previous=read(Path(path))
        return [{k:v for k,v in spec.items() if k!='sha256'} for spec in previous.get('score',{}).get('musical_locks',[]) if key(spec) in self.released_musical_keys]
    def edit_musical_locks(self):
        if self.busy or not self.score or not self.score.get('harmony'):self.message('Build or open a composed plan and wait for active work first.');return
        from lock_dialog import LockDialog
        dialog=LockDialog(self.score,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:self.apply_musical_locks(dialog.selections)
    def apply_musical_locks(self,selections):
        from commands import execute
        from musical_locks import key
        candidate=execute({'contract':1,'operation':'score.musical.locks.set','arguments':{'score':self.score,'selections':selections}})['result']
        before={key(spec) for spec in self.score.get('musical_locks',[])};after={key(spec) for spec in candidate.get('musical_locks',[])}
        self.released_musical_keys.update(before-after);self.released_musical_keys.difference_update(after)
        self.remember_plan();self.score=candidate;self.refresh_plan();self.message(f'{len(after)} musical decisions protected. Exact note locks remain separate; Undo is available.')
    def edit_melody_rhythm(self):
        if self.busy:self.message('Wait for the active operation before changing the melody rhythm.');return
        if not self.score or not self.score.get('harmony'):self.message('Build or open a composed plan with a harmonic timeline first.');return
        from rhythm_dialog import RhythmDialog
        dialog=RhythmDialog(self.score,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:self.apply_melody_rhythm(dialog.bars,dialog.pattern)
    def apply_melody_rhythm(self,bars,pattern):
        requested_state=self.recovery_signature()
        def applied(score):
            if self.recovery_signature()!=requested_state:self.message('Workspace changed while applying rhythm. Newer edits were kept.');return
            self.remember_plan();self.score=score;self.refresh_plan();self.message('Melody rhythm applied. Other parts and protected notes were preserved; Undo restores the previous phrase.')
        self.request('score.pattern.apply',{'score':deepcopy(self.score),'bars':bars,'pattern':pattern},applied)
    def remember_plan(self):self.history.remember(self.plan_state());self.output=None
    def undo_plan(self,redo=False):
        if self.busy:self.message('Wait for the active operation before changing edit history.');return
        state=(self.history.redo if redo else self.history.undo)(self.plan_state())
        if state is None:self.message('No further plan edits to '+('redo.' if redo else 'undo.'));return
        self.sections=state['sections'];self.score=state['score'];self.source_assets=state['source_assets'];self.output=None
        if self.score:self.bpm.setValue(self.score['bpm']);self.key.setCurrentIndex(self.score['root']);self.scale.setCurrentText(self.score['mode'])
        self.refresh_plan();self.message(('Redid' if redo else 'Undid')+' musical edit. Saved project files are unchanged until Save.')
    def plan(self):
        if self.score and (self.score.get('note_locks') or self.score.get('musical_locks')):self.message('Unlock protected musical decisions before replacing this composed plan. Existing edits can preserve the locks.');return
        initial=self.initial if self.initial is not None else self.brief.text();refined=self.brief.text() if self.initial is not None else None
        intent=interpret(initial,refined)
        if intent["state"]!="ready":
            if intent["state"]=="needs_input":self.initial=initial
            self.message(intent["message"]);return
        if intent["recommended_bpm"]:self.bpm.setValue(intent["recommended_bpm"])
        if "root" in intent["musical"]:self.key.setCurrentIndex(intent["musical"]["root"]);self.scale.setCurrentText(intent["musical"]["mode"])
        if self.mode.currentIndex()==1:
            try:
                score=compile_intent({"bpm":self.bpm.value(),"seconds":intent["seconds"],"root":self.key.currentIndex(),"mode":self.scale.currentText(),**intent["musical"]})
                self.remember_plan();self.score=score
                self.sections=[];self.source_assets={};self.refresh_plan();self.message(f"Built-in plan · {intent['seconds']:g}s · {self.bpm.value()} BPM. Edit notes before rendering.")
            except ValueError as error:self.message(str(error))
        else:
            args={"catalog":self.paths["catalog"].text(),"initial":initial}
            if refined is not None:args["refined"]=refined
            requested_state=self.recovery_signature()
            def planned(result):
                if self.recovery_signature()!=requested_state:self.message('Workspace or brief changed while planning. Build again to use the current request; newer edits were kept.');return
                if result["state"]=="ready":self.remember_plan();self.sections=result["sections"];self.score=None;self.source_assets={};self.refresh_plan();self.message("Plan ready. Audition samples and edit sections before rendering.")
                else:self.message(result["message"])
            self.request("brief.plan",args,planned)
    def ai_connection(self):
        if self.busy:self.message('Wait for active work before changing the AI connection.');return
        from ai_connection_dialog import ConnectionDialog
        if ConnectionDialog(self).exec()==QDialog.DialogCode.Accepted:
            self.ai_hint.setText('Local rules available · AI configured; verifying broker')
            self.request('ai.connection.check',{},lambda result:(self.ai_hint.setText('AI broker connected · audio stays local'),self.message('AI broker reachable. Use AI plan for a model-guided proposal.')))
    def ai_plan(self):
        if self.busy:return
        if self.score and (self.score.get('note_locks') or self.score.get('musical_locks')):self.message('Unlock protected musical decisions before replacing this plan.');return
        initial=self.initial if self.initial is not None else self.brief.text();refined=self.brief.text() if self.initial is not None else None
        parsed=interpret(initial,refined)
        if parsed['state']!='ready':
            if parsed['state']=='needs_input':self.initial=initial
            self.message(parsed['message']);return
        intent={'bpm':parsed.get('recommended_bpm') or self.bpm.value(),'seconds':parsed['seconds'],'root':self.key.currentIndex(),'mode':self.scale.currentText(),**parsed['musical']}
        args={'initial':initial,'intent':intent}
        if refined is not None:args['refined']=refined
        builtin=self.mode.currentIndex()==1
        if not builtin:args['catalog']=self.paths['catalog'].text()
        signature=self.recovery_signature()
        def planned(result):
            if self.recovery_signature()!=signature:self.message('Workspace changed during AI planning. Newer edits were kept.');return
            if result['state']!='ready':self.message(result['message']);return
            self.remember_plan();self.score=result.get('score');self.sections=result.get('sections',[]);self.source_assets=result.get('source_assets',{})
            if self.score:self.bpm.setValue(self.score['bpm']);self.key.setCurrentIndex(self.score['root']);self.scale.setCurrentText(self.score['mode'])
            self.refresh_plan();self.ai_hint.setText('AI proposal validated locally · audio stays local');self.message('AI plan ready for review and rendering. Musical timing, harmony and source identities were validated locally.')
        self.request('ai.score.plan' if builtin else 'ai.samples.plan',args,planned)
    def search_library(self):self.request("catalog.search",{"catalog":self.paths["catalog"].text(),"term":self.search.text(),"limit":100},self.populate_library)
    def recommend_samples(self):
        arguments={'catalog':self.paths['catalog'].text(),'term':self.search.text(),'bpm':self.bpm.value(),'limit':24}
        if self.score:arguments.update(root=self.score['root'],mode=self.score['mode'])
        def ranked(report):
            self.populate_library([{**item['catalog_observation'],'ranking':item} for item in report['candidates']])
            for row,item in enumerate(report['candidates']):self.library.item(row,0).setToolTip('\n'.join(item['reasons']))
            self.message(f"Recommended {len(report['candidates'])} samples from {report['catalog_rows_considered']} stored entries. Role/key are filename hints; review tempo alternatives before matching.")
        self.request('catalog.rank',arguments,ranked)
    def populate_library(self,result):
        self.samples=result;self.library.setRowCount(len(result))
        for row,sample in enumerate(result):
            ranking=sample.get('ranking');measurement=sample.get('tempo_measurement')
            value=ranking['bpm'] if ranking else sample.get('tempo_correction') or sample.get('bpm_hint') or (measurement or {}).get('bpm')
            label=QTableWidgetItem(f'{value:g}' if value is not None else 'Review' if ranking else '—')
            label.setToolTip('\n'.join(ranking['reasons']) if ranking else 'User correction (stat-pinned)' if sample.get('tempo_correction') else 'Filename hint; inspect embedded/audio evidence and half/double ambiguity.' if sample.get('bpm_hint') else 'Heuristic audio estimate; inspect confidence and ambiguity.' if measurement else 'Tempo not yet established.')
            self.library.setItem(row,0,QTableWidgetItem(sample["name"]));self.library.setItem(row,1,label)
        self.message(f"{len(result)} samples on this page. Narrow the search for specific results.")
    def scan_folder(self):
        folder=QFileDialog.getExistingDirectory(self,"Connect sample folder")
        if not folder:return
        if not self.paths["catalog"].text():self.paths["catalog"].setText(str(DATA/"catalog.sqlite"))
        self.request("catalog.scan",{"catalog":self.paths["catalog"].text(),"root":folder,"metadata_only":True},lambda result:self.message(f"Indexed {result['indexed']} files; {result['skipped']} skipped. Originals unchanged."))
    def sample(self):
        row=self.library.currentRow();return self.samples[row] if 0<=row<len(self.samples) else None
    def selected_sample(self):
        sample=self.sample()
        if not sample:return
        self.display_waveform(self.waveforms.get(sample["name"]))
        measured=sample.get("tempo_measurement")
        correction=sample.get('tempo_correction_record');review=f"{correction['bpm']:g} (review source identity)" if correction and not correction['valid'] else sample.get('tempo_correction') or 'none'
        self.observation.setText(f"Filename hint: {sample.get('bpm_hint') or 'unknown'} BPM\nAudio estimate: {measured['bpm'] if measured else 'not analyzed'}\nCorrection: {review}\nConfidence is heuristic, not a calibrated probability.")
        annotation=sample.get('musical_annotation')
        if annotation:self.observation.setText(self.observation.text()+'\nMusical tags: '+(annotation.get('role') or 'role unchanged')+' · '+('valid catalog identity' if annotation['valid'] else 'source changed; review required'))
        self.corrected.setValue(sample.get("tempo_correction") or sample.get("bpm_hint") or 120)
    def correct_tempo(self):
        sample=self.sample()
        if sample:self.request("catalog.correct",{"catalog":self.paths["catalog"].text(),"path":sample["path"],"bpm":self.corrected.value()},lambda result:self.message("Correction stored separately from original observations."))
    def hash_sample(self):
        sample=self.sample()
        if not sample:self.message('Select a catalog sample to identify its content.');return
        def hashed(result):
            sample['content_identity']={**result,'matches_catalog_stat':True,'live_content_verified':False}
            self.message('Audio content identified · SHA256 '+result['sha256']+'. Sources are unchanged; later file changes require a fresh hash.')
        self.request('catalog.hash',{'catalog':self.paths['catalog'].text(),'path':sample['path']},hashed)
    def relocate_catalog_sample(self):
        sample=self.sample()
        if not sample:return
        identity=sample.get('content_identity')
        if not identity or not identity['matches_catalog_stat']:self.message('Hash this catalog entry before selecting an identical replacement location.');return
        replacement=QFileDialog.getOpenFileName(self,'Locate identical audio; update catalog only',str(DATA))[0]
        if not replacement:return
        def relocated(result):
            self.search_library();self.message('Catalog location updated after identical-content verification. Audio files and saved project pins are unchanged; relink projects separately.')
        self.request('catalog.relocate',{'catalog':self.paths['catalog'].text(),'path':sample['path'],'replacement':replacement,'expected_sha256':identity['sha256']},relocated)
    def correct_musical_tags(self):
        sample=self.sample()
        if not sample:self.message('Select a sample to correct its musical role or key.');return
        identity=sample.get('content_identity')
        if not identity or not identity['matches_catalog_stat']:self.message('Hash the selected audio before making content-pinned musical corrections.');return
        dialog=QDialog(self);dialog.setWindowTitle('Correct sample musical role / key');form=QFormLayout(dialog)
        from retrieval import features
        hints=features(sample['name']);prior=sample.get('musical_annotation')
        note_names=('C','C♯','D','D♯','E','F','F♯','G','G♯','A','A♯','B')
        hint_key=note_names[hints['key']['root']]+' '+hints['key']['mode'] if hints['key'] else 'unknown key'
        prior_key=note_names[prior['root']]+' '+prior['mode'] if prior and prior.get('root') is not None else 'key unchanged'
        prior_text=(prior.get('role') or 'role unchanged')+' · '+prior_key+(' · source requires review' if not prior['valid'] else '') if prior else 'none'
        description=QLabel('Original filename hints stay separate from your corrections. Audio content is verified before accepting changes. Key means tonic/mode; it does not establish the chord progression.\n\nFilename suggests: '+hints['role']+' · '+hint_key+'\nYour saved correction: '+prior_text)
        description.setWordWrap(True);description.setTextFormat(Qt.TextFormat.PlainText);description.setMaximumWidth(600);form.addRow(description)
        role=QComboBox();role.setAccessibleName('Corrected sample role');role.addItem('Keep existing role',None)
        for value in ('drum','bass','chords','melody','fx','unknown'):role.addItem(value,value)
        key=QComboBox();key.setAccessibleName('Corrected sample key');key.addItem('Keep existing key',None)
        for root,name in enumerate(('C','C♯','D','D♯','E','F','F♯','G','G♯','A','A♯','B')):
            for mode in ('major','minor'):key.addItem(name+' '+mode,(root,mode))
        form.addRow('Role',role);form.addRow('Key',key)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel);form.addRow(buttons);buttons.rejected.connect(dialog.reject)
        def apply():
            args={'catalog':self.paths['catalog'].text(),'path':sample['path'],'expected_sha256':identity['sha256']}
            if role.currentData() is not None:args['role']=role.currentData()
            if key.currentData() is not None:args['root'],args['mode']=key.currentData()
            if len(args)==3:description.setText('Choose a role and/or complete key to correct. Existing valid properties are preserved.');return
            dialog.accept()
            def corrected(result):
                sample['musical_annotation']=result;self.message('Musical correction stored with verified content identity and dated history. Ranking distinguishes it from filename hints.')
            self.request('catalog.annotate',args,corrected)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(apply);dialog.exec()
    def measure_tempo(self):
        sample=self.sample()
        if sample:self.request("catalog.measure",{"catalog":self.paths["catalog"].text(),"path":sample["path"]},lambda result:self.message(f"Estimate: {result['tempo_measurement']['bpm']} BPM. Review half/double-time ambiguity."))
    def read_metadata(self):
        sample=self.sample()
        if not sample:return
        def loaded(result):
            sample.update(result);self.selected_sample()
            metadata=result['embedded_metadata'];observations=metadata['acid']
            self.message("Embedded ACID observations: "+json.dumps(observations,ensure_ascii=False) if observations else "Metadata inspected; no ACID tempo was found. Audio/filename evidence remains separate.")
        self.request('catalog.metadata',{'catalog':self.paths['catalog'].text(),'path':sample['path']},loaded)
    def add_sample(self):
        sample=self.sample()
        if not sample:return
        if len(self.sections)>=16:self.message("The arrangement supports sixteen sections.");return
        remaining=self.score["duration_frames"]/44100-sum(section["seconds"] for section in self.sections) if self.score else 4
        if remaining<0.1:self.message("The sample bed already fills the composed duration. Edit or remove a section first.");return
        self.remember_plan();self.sections.append({"sample":sample["name"],"seconds":min(4,remaining)});self.refresh_plan()
    def audition(self):
        sample=self.sample()
        if sample:self.play_file(sample["path"],10)
    def preview_waveform(self):
        sample=self.sample()
        if not sample:self.message("Select a sample first.");return
        def loaded(result):
            self.waveforms[sample["name"]]=result
            while len(self.waveforms)>32:del self.waveforms[next(iter(self.waveforms))]
            self.display_waveform(result)
            self.draw_timeline();self.message(f"Waveform preview · first{result['preview_seconds']:.1f}s · in memory only. Add this sample to see it on the timeline.")
        self.request("assets.waveform",{"path":sample["path"]},loaded)
    def display_waveform(self,result=None):
        self.waveform_scene.clear();self.waveform_scene.setSceneRect(0,0,256,64)
        if result:
            self.waveform_caption.setText(f"Preview: first{result['preview_seconds']:.1f}s of{result['source_seconds']:.1f}s · memory only")
            for index,(low,high) in enumerate(result["peaks"]):
                x=index*256/len(result["peaks"]);self.waveform_scene.addLine(x,32-max(-1,min(1,high))*28,x,32-max(-1,min(1,low))*28,QPen(QColor("#79ddd0")))
        else:
            self.waveform_caption.setText("Select a sample, then preview its waveform.")
            self.waveform_scene.addLine(0,32,256,32,QPen(QColor("#304354")))
        self.waveform_view.fitInView(self.waveform_scene.sceneRect(),Qt.AspectRatioMode.IgnoreAspectRatio)
    def play_file(self,path,seconds=None):
        self.stop_preview();args=["-nodisp","-autoexit","-loglevel","error"]
        if seconds:args.extend(("-t",str(seconds)))
        from audio_tools import file_inputs
        command=file_inputs(['ffplay',*args,str(path)]);self.preview_process.start(command[0],command[1:])
    def preview(self):
        if self.output:self.play_file(self.output)
        else:self.message("Render a plan to preview its music.")
    def show_output_levels(self):
        path=Path(self.output) if self.output else Path(self.selected_job()['folder'])/'result.mp3' if self.selected_job() else None
        if path is None or not path.is_file():self.message('Render or select a saved result first.');return
        def display(report):
            self.output_measurements=report;self.measurement_path=path
            def value(key,unit):return f"{report[key]:.1f} {unit}" if report.get(key) is not None else 'Not available for this content'
            text=(f"Decoded duration: {report['decoded_seconds']:.3f} seconds\n"
                  f"Integrated loudness: {value('integrated_lufs','LUFS')}\n"
                  f"True peak: {value('true_peak_dbtp','dBTP')}\n"
                  f"Sample peak: {value('sample_peak_dbfs','dBFS')}\n"
                  f"RMS level: {value('rms_dbfs','dBFS')}\n\n"
                  'These are measurements; no loudness normalization was applied. Short or below-gate content may not have an integrated loudness value.')
            if report['silent']:text+='\n\nOutput is silent. Review mute, routing and plugin gain settings.'
            if 'true_peak_above_zero' in report['warnings']:text+='\n\nTrue peak exceeds digital full scale; reduce the mix level and render again.'
            dialog=QMessageBox(self);dialog.setWindowTitle('Output measurements');dialog.setTextFormat(Qt.TextFormat.PlainText);dialog.setText(text);dialog.exec()
        stat=path.stat();cached=self.output_measurements
        if path==self.measurement_path and cached and (stat.st_size,stat.st_mtime_ns)==(cached['source_bytes'],cached['source_modified_ns']):display(cached)
        else:self.request('audio.inspect',{'path':str(path)},display)
    def stop_preview(self):
        if self.preview_process.state()!=QProcess.ProcessState.NotRunning:self.preview_process.kill();self.preview_process.waitForFinished(1000)
    def refresh_plan(self):
        self.loading=True;self.section_table.setRowCount(len(self.sections))
        for row,section in enumerate(self.sections):
            self.section_table.setItem(row,0,QTableWidgetItem(section["sample"]));self.section_table.setItem(row,1,QTableWidgetItem(str(section["seconds"])))
            if "source_bpm" in section:self.section_table.item(row,0).setToolTip(f"{section['source_bpm']:g} BPM × {section['beat_scale']:g} → {section['target_bpm']:g} BPM; pitch-preserving stretch, downbeat not inferred.")
        notes=self.score["notes"] if self.score else [];self.notes.setRowCount(len(notes))
        locked={note_identity(note) for note in (self.score or {}).get('note_locks',[])}
        for row,note in enumerate(notes):
            for column,key in enumerate(("part","tick","length","pitch","velocity")):
                item=QTableWidgetItem(str(note[key]))
                if note_identity(note) in locked:item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable);item.setToolTip('Locked note. Use Lock / unlock selected note before editing.');item.setForeground(QColor('#f0d489'))
                self.notes.setItem(row,column,item)
        harmony=(self.score or {}).get('harmony',[]);self.harmony_table.setRowCount(len(harmony))
        for row,chord in enumerate(harmony):
            for column,text in enumerate((str(row+1),str(chord['degree']),chord_label(self.score,chord),', '.join(map(str,chord['pitches'])))):
                item=QTableWidgetItem(text)
                if column!=1:item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable)
                item.setToolTip('Edit degree1–7 within the accepted key. Revoicing preserves timing and exact note locks.');self.harmony_table.setItem(row,column,item)
        self.loading=False;self.fit_timeline()
    def harmony_edited(self,item):
        if self.loading or not self.score or item.column()!=1:return
        if self.busy:self.message('Wait for active processing before editing harmony.');self.refresh_plan();return
        try:
            from commands import execute
            candidate=execute({'contract':1,'operation':'score.harmony.edit','arguments':{'score':self.score,'changes':[{'bar':item.row(),'degree':int(item.text())}]}})['result']
            if candidate==self.score:return
            row=item.row();self.remember_plan();self.score=candidate;self.refresh_plan();self.harmony_table.selectRow(row);self.message('Harmonic intention revoiced. Rhythm, unrelated notes and compatible locked events are preserved. Undo is available.')
        except ValueError as error:self.message(str(error));self.refresh_plan()
    def section_edited(self,item):
        if self.loading:return
        try:
            updated=deepcopy(self.sections)
            for row,section in enumerate(updated):section.update(sample=self.section_table.item(row,0).text(),seconds=float(self.section_table.item(row,1).text()))
            from render import resolve_sections
            resolve_sections(updated,Path(self.paths["catalog"].text()),resolver=self.resolve_sample)
            if sum(s["seconds"] for s in updated)>240:raise ValueError("The arrangement must fit four minutes.")
            self.remember_plan();self.sections=updated;self.draw_timeline()
        except (ValueError,OSError,sqlite3.Error) as error:self.message(str(error));self.refresh_plan()
    def note_edited(self,item):
        if self.loading or not self.score:return
        try:
            key=("part","tick","length","pitch","velocity")[item.column()]
            self.apply_note_changes([{'action':'set','index':item.row(),'field':key,'value':item.text() if key=='part' else int(item.text())}],item.row(),refresh=False)
        except ValueError as error:self.message(str(error));self.refresh_plan()
    def apply_note_changes(self,changes,index,refresh=True):
        try:
            from commands import execute
            candidate=execute({'contract':1,'operation':'score.edit','arguments':{'score':self.score,'changes':changes}})['result']
            if candidate['notes']==self.score['notes']:
                self.draw_timeline();return
            self.remember_plan();self.score=candidate
            if refresh:self.refresh_plan();self.notes.selectRow(index)
            else:self.draw_timeline()
            self.message('Note edit accepted. Undo is available; saved files change only on Save.')
        except ValueError as error:self.message(str(error));self.refresh_plan()
    def toggle_note_lock(self):
        row=self.notes.currentRow()
        if self.busy or not self.score or not 0<=row<len(self.score['notes']):self.message('Select a note and wait for active work first.');return
        from commands import execute
        locked={note_identity(note) for note in self.score.get('note_locks',[])}
        indices=[index for index,note in enumerate(self.score['notes']) if note_identity(note) in locked]
        identity=note_identity(self.score['notes'][row])
        if row in indices:indices.remove(row);self.released_note_ids.add(identity)
        else:indices.append(row);self.released_note_ids.discard(identity)
        candidate=execute({'contract':1,'operation':'score.locks.set','arguments':{'score':self.score,'indices':indices}})['result']
        self.remember_plan();self.score=candidate;self.refresh_plan();self.notes.selectRow(row);self.message(f'{len(indices)} exact note events locked. Other edits preserve their timing, pitch and velocity; Undo is available.')
    def select_section(self,index):self.section_table.selectRow(index)
    def resize_section(self,index,length):
        step=60/self.bpm.value()/4 if self.snap.isChecked() else 0.1;length=max(0.1,round(length/step)*step)
        if sum(s["seconds"] for i,s in enumerate(self.sections) if i!=index)+length>240:self.message("The arrangement must fit four minutes.");self.draw_timeline();return
        self.remember_plan();self.sections[index]["seconds"]=length;self.refresh_plan();self.select_section(index)
    def move_section(self,direction):
        row=self.section_table.currentRow();other=row+direction
        if 0<=row<len(self.sections) and 0<=other<len(self.sections):self.remember_plan();self.sections[row],self.sections[other]=self.sections[other],self.sections[row];self.refresh_plan();self.select_section(other)
    def match_tempo(self):
        row=self.section_table.currentRow()
        if not 0<=row<len(self.sections):self.message("Select a sample section first.");return
        section=self.sections[row];dialog=QDialog(self);dialog.setWindowTitle("Clip tempo interpretation");form=QFormLayout(dialog)
        enabled=QCheckBox("Match tempo for this clip");enabled.setChecked(True);form.addRow(enabled)
        source=QDoubleSpinBox();source.setRange(20,400);source.setDecimals(2);source.setValue(section.get("source_bpm",120));source.setAccessibleName("Interpreted source tempo")
        target=QDoubleSpinBox();target.setRange(20,400);target.setDecimals(2);target.setValue(section.get("target_bpm",self.bpm.value()));target.setAccessibleName("Target clip tempo")
        scale=QComboBox();scale.addItems(["Half-time ×0.5","As written ×1","Double-time ×2"]);scale.setCurrentIndex((0.5,1,2).index(section.get("beat_scale",1)));scale.setAccessibleName("Half or double time interpretation")
        form.addRow("Source BPM",source);form.addRow("Interpretation",scale);form.addRow("Target BPM",target)
        help=QLabel("This changes only the clip. Original hints, measured confidence and catalog corrections remain separate. Tempo matching preserves pitch; it does not find the downbeat.");help.setWordWrap(True);form.addRow(help)
        preview=QLabel();form.addRow(preview)
        def describe():
            rate=target.value()/(source.value()*(0.5,1,2)[scale.currentIndex()]);preview.setText(f"Playback rate {rate:.4f}× · "+("supported" if 0.5<=rate<=2 else "outside supported0.5–2× range"))
        source.valueChanged.connect(describe);target.valueChanged.connect(describe);scale.currentIndexChanged.connect(describe);describe()
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);form.addRow(buttons);buttons.rejected.connect(dialog.reject)
        def accept():
            candidate=deepcopy(section)
            for key in ("source_bpm","target_bpm","beat_scale"):candidate.pop(key,None)
            if enabled.isChecked():candidate.update(source_bpm=source.value(),target_bpm=target.value(),beat_scale=(0.5,1,2)[scale.currentIndex()])
            try:
                from render import resolve_sections
                resolve_sections([candidate],Path(self.paths["catalog"].text()),resolver=self.resolve_sample)
                self.remember_plan();self.sections[row]=candidate;self.refresh_plan();dialog.accept();self.message("Clip tempo interpretation saved. Catalog evidence is unchanged.")
            except (ValueError,OSError,sqlite3.Error) as error:preview.setText(str(error))
        buttons.accepted.connect(accept);dialog.exec()
    def remove_section(self):
        row=self.section_table.currentRow()
        if 0<=row<len(self.sections):self.remember_plan();self.sections.pop(row);self.refresh_plan()
    def duration(self):return self.score["duration_frames"]/44100 if self.score else sum(section["seconds"] for section in self.sections)
    def fit_timeline(self):self.pixels_per_second=max(2,min(100,(self.timeline.viewport().width()-40)/max(4,self.duration())));self.draw_timeline()
    def draw_timeline(self):
        self.locked_note_signatures={note_identity(note) for note in (self.score or {}).get('note_locks',[])}
        self.scene.clear();duration=max(1,self.duration()) if self.score or self.sections else 10;width=max(640,duration*self.pixels_per_second+40);hybrid=bool(self.score and self.sections);self.scene.setSceneRect(0,0,width,420 if hybrid else 340)
        for second in range(0,int(duration)+1,1 if duration<10 else 5):
            x=second*self.pixels_per_second+16;self.scene.addLine(x,32,x,330,QPen(QColor("#1e3242")))
            label=self.scene.addText(f"{second}s");label.setDefaultTextColor(QColor("#a7bfd0"));label.setPos(x,2)
        position=16
        for index,section in enumerate(self.sections):self.scene.addItem(Clip(self,index,position,section["seconds"]*self.pixels_per_second,section));position+=section["seconds"]*self.pixels_per_second
        if self.score:
            colors={"bass":"#66c5ba","chords":"#7ea5e8","melody":"#d4b177"};tick_seconds=60/(self.score["bpm"]*self.score["tpq"])
            bar=0
            for section in self.score.get('form',[]):
                x=16+bar*3840*tick_seconds*self.pixels_per_second;span=min(section['bars']*3840*tick_seconds,duration-bar*3840*tick_seconds)*self.pixels_per_second
                if span>0:
                    marker=self.scene.addRect(x,31,span,23,QPen(QColor('#41566a')),QBrush(QColor('#203748')))
                    marker.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemClipsChildrenToShape)
                    text=self.scene.addText(section['role'].upper());text.setParentItem(marker);text.setDefaultTextColor(QColor('#c2d3e1'));text.setPos(x+3,31)
                    marker.setToolTip(f"{section['role']} · {section['bars']} bars · {section['density']} · "+', '.join(section['parts']))
                bar+=section['bars']
            for index,note in enumerate(self.score["notes"]):
                x=16+note["tick"]*tick_seconds*self.pixels_per_second;y=(150+(84-note["pitch"])*3) if hybrid else 70+(84-note["pitch"])*4
                self.scene.addItem(NoteClip(self,index,note,x,y,note['length']*tick_seconds*self.pixels_per_second,colors[note['part']]))
            for index,chord in enumerate(self.score.get('harmony',[])):
                start=chord['bar']*3840*tick_seconds;span=min(3840*tick_seconds,max(0,duration-start))
                if span>0:self.scene.addItem(HarmonyClip(self,index,chord,16+start*self.pixels_per_second,128 if hybrid else 54,span*self.pixels_per_second))
        if not self.sections and not self.score:
            text=self.scene.addText("Your arrangement starts here.\nBuild a plan or add a sample from the library.");text.setDefaultTextColor(QColor("#9fb6c9"));text.setPos(24,90)
        if self.paths.get("voice") and self.paths["voice"].text():
            voice_y=370 if hybrid else 292
            offset=self.voice_offset.value();x=16+offset*self.pixels_per_second
            report=self.voice_report;source=Path(self.paths['voice'].text());checked=False
            if report and report['path']==str(source.resolve()) and source.is_file():
                stat=source.stat();checked=(stat.st_size,stat.st_mtime_ns)==(report['bytes'],report['modified_ns'])
            length=report['decoded_frames']/44100 if checked else 0
            width=max(8,length*self.pixels_per_second)
            self.scene.addRect(x,voice_y,width,28,QPen(QColor("#d8b875")),QBrush(QColor("#51442b")))
            caption=f"NARRATION @{offset:g}s · "+(f"{length:g}s" if checked else 'check placement for length')
            text=self.scene.addText(caption);text.setDefaultTextColor(QColor("#f3dfb5"));text.setPos(x+6,voice_y)

    def processing(self):
        result={key:self.paths[key].text() for key in ("worker","plugin","state") if self.paths[key].text()}
        if not result.get("plugin"):return {"worker":result["worker"]} if self.instruments and result.get("worker") else {}
        if result.get("plugin") and self.classes.currentIndex()>=0 and self.plugin_inventory:
            result["class_id"]=self.plugin_inventory[self.classes.currentIndex()]["class_id"]
        elif result.get('plugin') and self.saved_effect_class_id:result['class_id']=self.saved_effect_class_id
        return result
    def asset_bindings(self):
        names={section['sample'] for section in self.sections}
        return {name:asset for name,asset in self.source_assets.items() if name in names} or None
    def voice_options(self):return {'offset_seconds':self.voice_offset.value(),'voice_gain_db':self.voice_gain.value(),'music_gain_db':self.music_gain.value(),'ducking':self.ducking.isChecked()}
    def check_voice(self):
        if not self.paths['voice'].text() or not self.duration():self.message('Choose narration and build an arrangement first.');return
        def checked(result):
            self.voice_report=result;self.draw_timeline();self.message(f"Voice fits · {result['decoded_frames']/44100:g}s decoded · starts at {result['offset_samples']/44100:g}s.")
        self.request('narration.inspect',{'voice':self.paths['voice'].text(),'seconds':self.duration(),'voice_settings':self.voice_options()},checked)
    def narration_arguments(self):
        path=self.paths['voice'].text()
        return {'voice':Path(path),'voice_settings':self.voice_options(),'voice_asset':self.voice_asset} if path else {}
    def processing_bindings(self):return {'expected_processing':self.expected_processing,'expected_instruments':self.expected_instruments}
    def resolve_sample(self,name):
        if name in self.source_assets:return Path(self.source_assets[name]['path'])
        from render import catalog_music
        return catalog_music(Path(self.paths['catalog'].text()),name)
    def save_project(self):
        if self.active_operation=="continuous.play":self.message("Continuous audio cannot be saved. Stop temporary playback to edit a normal project.");return
        path=self.project_path or QFileDialog.getSaveFileName(self,"Save project",str(DATA/"arrangement.json"),"Arranger projects (*.json)")[0]
        if not path:return
        try:
            releases=[]
            if Path(path).is_file() and self.released_note_ids:
                from project import read
                prior=read(Path(path))
                releases=[index for index,note in enumerate(prior.get('score',{}).get('notes',[])) if note_identity(note) in self.released_note_ids and note in prior.get('score',{}).get('note_locks',[])]
            result=save_project(Path(path),self.sections,Path(self.paths["catalog"].text()) if self.paths["catalog"].text() else None,
                 expected_revision=self.revision if self.project_path else 0,brief={"initial":self.initial or self.brief.text(),"effective":self.brief.text()},processing=self.processing(),score=self.score,parameters=self.parameters,instruments=self.instruments,source_assets=self.asset_bindings(),released_note_indices=releases,released_musical_locks=self.musical_releases(path),**self.narration_arguments(),**self.processing_bindings())
            from project import processing_pins
            pins=processing_pins(result);self.expected_processing=pins['processing'];self.expected_instruments=pins['instruments']
            self.project_path=path;self.revision=result["revision"];self.message(f"Project saved · revision {self.revision}")
            self.released_note_ids.clear();self.released_musical_keys.clear()
            self.mark_workspace_saved();return True
        except (ValueError,OSError) as error:self.message(str(error))
    def open_project(self):
        if self.active_operation=="continuous.play":self.message("Stop temporary playback before reopening a normal project.");return
        path=QFileDialog.getOpenFileName(self,"Open project",str(DATA),"Arranger projects (*.json)")[0]
        if not path:return
        self.load_project(path)
    def load_project(self,path):
        if self.busy:self.message('Finish or stop active work before opening a project.');return False
        try:
            from project import inspect
            report=inspect(Path(path));project=report['project']
            if project['schema']==7:
                self.open_routing(project,path);return True
            if not self.confirm_workspace_replacement():return False
            self.sections=project["sections"];self.score=project.get("score");self.project_path=path;self.revision=project["revision"]
            self.history.clear()
            self.released_note_ids.clear();self.released_musical_keys.clear()
            from project import processing_pins
            pins=processing_pins(project);self.expected_processing=pins['processing'];self.expected_instruments=pins['instruments']
            self.source_assets={section['sample']:asset for section,asset in zip(self.sections,project['assets'])}
            narration=project.get('narration')
            self.voice_asset={key:narration[key] for key in ('path','bytes','sha256')} if narration else None
            self.paths['voice'].setText(narration['path'] if narration else '')
            from narration import settings
            options=settings(narration['settings'] if narration else None)
            self.voice_offset.setValue(options['offset_seconds']);self.voice_gain.setValue(options['voice_gain_db']);self.music_gain.setValue(options['music_gain_db']);self.ducking.setChecked(options['ducking'])
            self.paths["catalog"].setText(project.get("catalog") or "")
            for key in ("worker","plugin","state"):self.paths[key].setText(project.get("processing",{}).get(key,{}).get("path",""))
            if not self.paths['worker'].text() and native_tool('arranger-vst3.exe').is_file():self.paths['worker'].setText(str(native_tool('arranger-vst3.exe')))
            self.parameters=project.get("parameters",{})
            self.restore_effect_selection(project.get('processing',{}).get('class_id'),self.parameters)
            self.instruments=project.get("instruments",{});self.refresh_instruments()
            saved_brief=project.get('brief') or {};self.brief.setText(saved_brief.get('effective',''));self.initial=saved_brief.get('initial') if saved_brief.get('initial')!=saved_brief.get('effective') else None
            if self.score:self.bpm.setValue(self.score["bpm"]);self.key.setCurrentIndex(self.score["root"]);self.scale.setCurrentText(self.score["mode"]);self.mode.setCurrentIndex(1)
            else:self.mode.setCurrentIndex(0)
            self.refresh_plan();self.message(f"Project reopened · revision {self.revision}" if report['ready'] else "Project opened for recovery. Missing/changed assets block rendering; select a section and relink identical content. "+json.dumps(report['issues']))
            self.mark_workspace_saved();return True
        except (ValueError,OSError) as error:self.message(str(error));return False
    def package_project(self):
        if self.busy or self.active_operation=='continuous.play':self.message('Finish active work before copying a saved project.');return
        if not self.project_path:self.message('Save the project before packaging its exact revision.');return
        if self.recovery_signature()!=self.recovery_baseline:self.message('Save unsaved workspace edits before packaging the saved revision.');return
        destination=QFileDialog.getSaveFileName(self,'New portable project folder (must not exist)',str(DATA/'Portable arrangement'))[0]
        if not destination:return
        def packaged(result):self.message(f"Portable project copied · {result['files']} audio/state assets. Plugins/activation are separate. Original files and saved jobs are unchanged.")
        self.request('project.bundle.export',{'project':self.project_path,'destination':destination},packaged)
    def import_project_package(self):
        if self.busy or self.active_operation=='continuous.play':self.message('Finish active work before opening a portable project.');return
        folder=QFileDialog.getExistingDirectory(self,'Open a portable project folder',str(DATA))
        if not folder:return
        def inspected(summary):
            destination=QFileDialog.getSaveFileName(self,'New folder for the reopened project (must not exist)',str(DATA/'Reopened arrangement'))[0]
            if not destination:return
            # Only exact locally available identities can be rebound automatically.
            # Missing externals remain explicit recovery issues, never downloads.
            candidates={'worker':[value for value in (str(native_tool('arranger-vst3.exe')),self.paths['worker'].text()) if value],
                        'plugin':[value for value in [self.paths['plugin'].text()]+[spec['plugin'] for spec in self.instruments.values()] if value]}
            def opened(result):
                if not self.load_project(result['project_path']):self.message('Portable copy created at '+result['project_path']+'. Current workspace kept.');return
                if not result['ready']:self.message('Portable project opened for recovery. Select matching installed plugin/worker bindings; nothing was downloaded or activated. '+json.dumps(result['issues']))
            def matched(result):self.request('project.bundle.import',{'package':folder,'destination':destination,'expected_manifest_sha256':summary['manifest_sha256'],'bindings':result['bindings']},opened)
            self.request('project.bundle.match',{'package':folder,'expected_manifest_sha256':summary['manifest_sha256'],'available_assets':candidates},matched)
        self.request('project.bundle.inspect',{'package':folder},inspected)
    def open_routing(self,project=None,path=None):
        if self.busy:self.message('Stop or finish the active operation before editing routing.');return
        # A button's clicked(bool) is not a project descriptor.
        from routing_workspace import RoutingWorkspace
        dialog=RoutingWorkspace(self,project if isinstance(project,dict) else None,path)
        dialog.exec()
    def relink_sample(self):
        if self.busy:self.message("Wait for the active job first.");return
        row=self.section_table.currentRow()
        if not self.project_path or not 0<=row<len(self.sections):self.message("Open a saved project and select a sample section first.");return
        from project import read
        saved=read(Path(self.project_path));matches=[index for index,section in enumerate(saved['sections']) if section['sample']==self.sections[row]['sample']]
        if not matches:self.message("Save this new sample section before relinking it.");return
        path=QFileDialog.getOpenFileName(self,"Relink identical sample content",str(DATA))[0]
        if not path:return
        def loaded(report):
            project=report['project'];self.revision=project['revision']
            self.source_assets.update({section['sample']:asset for section,asset in zip(project['sections'],project['assets'])})
            self.waveforms.clear();self.draw_timeline();self.message("Sample location updated; musical edits are preserved. "+("Project assets are ready." if report['ready'] else "Other missing assets still require recovery."))
        self.request('project.relink',{'project':self.project_path,'expected_revision':self.revision,'replacements':{str(matches[0]):path}},loaded)
    def review_processing(self):
        if not self.project_path:self.message('Save or open a project first.');return
        def reviewed(report):
            if report['revision']!=self.revision:self.message('Project revision changed. Reopen it before reviewing updates.');return
            if not report['changes']:self.message('Saved processing content is unchanged.');return
            dialog=QDialog(self);dialog.setWindowTitle('Review processing content changes');dialog.resize(760,430)
            layout=QVBoxLayout(dialog);label=QLabel('Select changed files to adopt into this saved project. This updates exact content identities and keeps a dated history. It does not certify compatibility. Missing files cannot be adopted. Musical edits in the workspace are preserved.')
            label.setWordWrap(True);layout.addWidget(label)
            table=QTableWidget(len(report['changes']),3);table.setHorizontalHeaderLabels(['Adopt','Asset','SHA256 before → now'])
            table.setAccessibleName('Processing content changes');table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
            for index,change in enumerate(report['changes']):
                choice=QTableWidgetItem();choice.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable);choice.setCheckState(Qt.CheckState.Unchecked)
                if change['current_sha256'] is None:choice.setFlags(Qt.ItemFlag.NoItemFlags)
                table.setItem(index,0,choice)
                for column,text in ((1,change['selector']),(2,change['previous_sha256']+' → '+(change['current_sha256'] or 'MISSING'))):
                    item=QTableWidgetItem(text);item.setToolTip(change['path']+'\n'+text);item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable);table.setItem(index,column,item)
            layout.addWidget(table);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(buttons)
            buttons.rejected.connect(dialog.reject)
            def apply():
                updates={change['selector']:change['current_sha256'] for index,change in enumerate(report['changes']) if table.item(index,0).checkState()==Qt.CheckState.Checked}
                if not updates:label.setText('Select at least one available changed asset to adopt.');return
                dialog.accept()
                def adopted(result):
                    from project import processing_pins
                    pins=processing_pins(result['project']);self.expected_processing=pins['processing'];self.expected_instruments=pins['instruments'];self.revision=result['project']['revision']
                    self.message('Reviewed processing identities updated. '+('Project assets ready.' if result['ready'] else 'Other missing or changed assets still block rendering.'))
                self.request('project.processing.adopt',{'project':self.project_path,'expected_revision':self.revision,'updates':updates},adopted)
            buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(apply);dialog.exec()
        self.request('project.processing.review',{'project':self.project_path},reviewed)
    def render_job(self):
        if self.busy:return
        if not self.sections and not self.score:self.message("Build a plan first.");return
        path=None
        requested_state=self.recovery_signature()
        try:
            temporary=self.temporary_results.isChecked()
            jobs=self.result_jobs(reserve=True);jobs.mkdir(parents=True,exist_ok=True)
            descriptor,path=tempfile.mkstemp(prefix="arranger-project-snapshot-",suffix=".json");os.close(descriptor);Path(path).unlink();self.owned_snapshots.add(Path(path))
            processing=self.processing()
            if self.classes.currentIndex()>=0 and self.plugin_inventory:processing["class_id"]=self.plugin_inventory[self.classes.currentIndex()]["class_id"]
            save_project(Path(path),self.sections,Path(self.paths["catalog"].text()) if self.paths["catalog"].text() else None,processing=processing,score=self.score,parameters=self.parameters,instruments=self.instruments,
                         source_assets=self.asset_bindings(),**self.narration_arguments(),**self.processing_bindings(),
                         brief={"initial":self.initial or self.brief.text(),"effective":self.brief.text(),"refined":self.initial is not None})
            args={"project":path,"jobs":str(jobs)}
            if self.paths["voice"].text():args["voice"]=self.paths["voice"].text()
            def complete(result):
                self.output=result['audio'];self.output_measurements=result.get('measurements');self.measurement_path=Path(self.output)
                if self.recovery_signature()!=requested_state:self.message('Earlier workspace snapshot rendered. Your newer edits are kept and have not been rendered; Play result previews the earlier snapshot.');return
                self.message(f"Ready · {result['requested_seconds']:g}s · MP3 192 kbps. "+('Temporary until this workspace closes.' if temporary else 'Play the result to preview.')+(' Output is silent; check mute/routing/gain.' if (self.output_measurements or {}).get('silent') else ''))
            from assets import digest
            args.update(request_id=str(uuid.uuid4()),project_sha256=digest(Path(path)))
            if args.get('voice'):args['voice_sha256']=digest(Path(args['voice']))
            self.request("jobs.submit",args,complete)
        except (ValueError,OSError) as error:self.message(str(error))

    def inspect_plugin(self):
        def loaded(result):
            self.plugin_inventory=result["classes"];self.classes.blockSignals(True);self.classes.clear();self.classes.addItems([item["name"] for item in self.plugin_inventory])
            selected=next((i for i,item in enumerate(self.plugin_inventory) if item['class_id']==self.saved_effect_class_id),0)
            self.classes.setCurrentIndex(selected);self.classes.blockSignals(False);self.show_parameters();self.message("Plugin inventory loaded. Compatibility depends on the tested component and routing.")
        args={"worker":self.paths["worker"].text(),"plugin":self.paths["plugin"].text()}
        if self.paths["state"].text():args["state"]=self.paths["state"].text()
        self.request("plugins.inspect",args,loaded)

    def plugin_library(self):
        if self.busy:self.message('Wait for the active operation first.');return
        dialog=QDialog(self);dialog.setWindowTitle('Installed plugin library');dialog.resize(900,560);layout=QVBoxLayout(dialog)
        help=QLabel('Scan a folder containing installed Windows x64 VST3 plugins. This does not install software, accept agreements or certify compatibility. Unchanged failures stay quarantined until an explicit retry.')
        help.setWordWrap(True);layout.addWidget(help)
        table=QTableWidget(0,3);table.setHorizontalHeaderLabels(['Plugin bundle','Components','Status']);table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        table.setAccessibleName('Installed plugin inventory');table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);layout.addWidget(table)
        components=QComboBox();components.setAccessibleName('Registered plugin component');layout.addWidget(components)
        destination=QComboBox();destination.addItems(['Master effect','Bass','Chords','Melody']);destination.setAccessibleName('Plugin assignment destination');layout.addWidget(destination)
        detail=QLabel('Choose a plugin bundle. Instrument assignment uses main bus0; additional outputs remain available through the explicit assignment controls.');detail.setTextFormat(Qt.TextFormat.PlainText);detail.setWordWrap(True);layout.addWidget(detail)
        rows=[];registry=str(DATA/'plugins.sqlite')
        def selected():
            index=table.currentRow();return rows[index] if 0<=index<len(rows) else None
        def changed():
            record=selected();components.clear()
            if not record:return
            values=(record.get('report') or {}).get('classes',[])
            components.addItems([f"{item['name']} · "+('Instrument' if item['audio_inputs']==0 else 'Effect') for item in values])
            detail.setText(record['error'] if record.get('error') else 'Inventory only. Vendor activation/editor, routing and validator acceptance remain separate. Main bus0 will be selected.')
        table.itemSelectionChanged.connect(changed)
        def refresh():
            def listed(result):
                rows[:]=result;table.setRowCount(len(rows))
                for index,record in enumerate(rows):
                    for column,text in enumerate((Path(record['path']).name,str(len((record.get('report') or {}).get('classes',[]))),record['status'])):
                        item=QTableWidgetItem(text);item.setToolTip(record['path']);table.setItem(index,column,item)
                detail.setText(f'{len(rows)} registered bundles on this page. Scan a narrower folder to add or update plugins.')
            self.request('plugins.list',{'registry':registry,'limit':100},listed)
        def scan():
            root=QFileDialog.getExistingDirectory(dialog,'Scan installed plugin folder')
            if not root:return
            self.request('plugins.scan',{'registry':registry,'worker':self.paths['worker'].text(),'root':root},lambda result:refresh())
        def retry():
            record=selected()
            if not record or record['status']!='quarantined':detail.setText('Select a quarantined plugin first.');return
            detail.setText('Retrying the exact registered binary in its bounded worker…')
            self.request('plugins.retry',{'registry':registry,'worker':self.paths['worker'].text(),'plugin':record['path'],'expected_sha256':record['binary_sha256']},lambda result:refresh())
        def use():
            record=selected();index=components.currentIndex()
            if not record or record['status']!='ready' or index<0:detail.setText('Select an available component first.');return
            component=record['report']['classes'][index];part=destination.currentText().lower()
            if (part=='master effect')==(component['audio_inputs']==0):detail.setText('Choose an effect for the master, or an instrument for a musical part.');return
            if part!='master effect':
                self.instruments[part]={'plugin':record['path'],'class_id':component['class_id'],'outputs':[{'bus':0,'gain':1}]};self.refresh_instruments()
            else:
                self.paths['plugin'].setText(record['path']);self.paths['state'].clear();self.parameters={};self.plugin_inventory=[];self.classes.clear();self.parameter_table.setRowCount(0)
                def inspected(result):
                    self.plugin_inventory=result['classes'];self.classes.addItems([item['name'] for item in self.plugin_inventory]);self.show_parameters();self.message('Selected effect inspected. Render to evaluate this exact component.')
                self.request('plugins.inspect',{'worker':self.paths['worker'].text(),'plugin':record['path'],'class_id':component['class_id']},inspected)
            dialog.accept();self.message('Plugin assigned. Saved project content pins still apply; scan inventory is not a compatibility certificate.')
        row=QHBoxLayout()
        for caption,action in (('Scan folder…',scan),('Refresh',refresh),('Retry quarantined',retry),('Use selected component',use),('Close',dialog.reject)):
            row.addWidget(button(caption,action))
        layout.addLayout(row);refresh();dialog.exec()

    def preset_file(self,instrument,export):
        if self.busy:self.message("Wait for the active job first.");return
        spec=None
        if instrument:
            row=self.instrument_table.currentRow()
            if not 0<=row<3:self.message("Select an instrument part first.");return
            spec=self.instruments.get(("bass","chords","melody")[row])
            if not spec:self.message("Assign a VST3 instrument first.");return
        plugin=spec["plugin"] if spec else self.paths["plugin"].text()
        if not plugin:self.message("Choose a plugin first.");return
        args={"worker":self.paths["worker"].text(),"plugin":plugin}
        if export:
            if not spec and self.parameters:self.message("Save the queued parameter values before exporting a preset.");return
            state=spec.get("state") if spec else self.paths["state"].text()
            if not state:self.message("Save a state using the native editor before exporting.");return
            path=QFileDialog.getSaveFileName(self,"Export VST3 preset",str(DATA/"Sound.vstpreset"),"VST3 presets (*.vstpreset)")[0]
            if not path:return
            args.update(state=state,destination=path)
            if spec:args["class_id"]=spec["class_id"]
            self.request("plugins.preset.export",args,lambda result:self.message("VST3 preset exported. Existing files are preserved."))
        else:
            path=QFileDialog.getOpenFileName(self,"Import VST3 preset",str(DATA),"VST3 presets (*.vstpreset)")[0]
            if not path:return
            args.update(preset=path,presets=str(DATA/"presets"))
            def loaded(result):
                if spec:
                    if result["class_id"]!=spec["class_id"]:self.message("Preset belongs to another component; assignment unchanged.");return
                    spec["state"]=result["state"]
                else:
                    self.paths["state"].setText(result["state"]);self.plugin_inventory=[];self.classes.clear();self.parameter_table.setRowCount(0);self.parameters={}
                self.message("Preset imported. Inspect the plugin or open its editor to review the restored values.")
            self.request("plugins.preset.import",args,loaded)
    def restore_effect_selection(self,class_id,parameters):
        # A reopened component must not inherit a previously inspected bundle's
        # class or values. Rendering keeps the saved class even before inspection.
        self.saved_effect_class_id=class_id;self.parameter_class_id=class_id
        self.plugin_inventory=[];self.classes.clear();self.parameter_table.setRowCount(0);self.parameters=deepcopy(parameters)
    def show_parameters(self):
        index=self.classes.currentIndex()
        if not 0<=index<len(self.plugin_inventory):return
        class_id=self.plugin_inventory[index]['class_id']
        if self.parameter_class_id!=class_id:self.parameters={}
        self.parameter_class_id=class_id;self.saved_effect_class_id=class_id
        self.loading=True;values=self.plugin_inventory[index]["parameters"];self.parameter_table.setRowCount(len(values))
        for row,value in enumerate(values):
            label=QTableWidgetItem(value["name"]);label.setFlags(label.flags()&~Qt.ItemFlag.ItemIsEditable)
            self.parameter_table.setItem(row,0,label);self.parameter_table.setItem(row,1,QTableWidgetItem(str(self.parameters.get(str(value['id']),value["normalized"]))))
        self.loading=False
    def parameter_edited(self,item):
        if self.loading or item.column()!=1:return
        try:
            import math
            parameter=self.plugin_inventory[self.classes.currentIndex()]["parameters"][item.row()];value=float(item.text())
            if not math.isfinite(value) or not 0<=value<=1 or parameter["flags"]&2:raise ValueError("Parameter is read-only or outside zero-to-one range.")
            self.parameters[str(parameter["id"])]=value;self.message("Parameter edit queued for rendering. Save parameter state or open the native editor to create a preset.")
        except (ValueError,IndexError) as error:self.message(str(error));self.show_parameters()
    def open_native(self,interactive=True):
        index=self.classes.currentIndex()
        if not 0<=index<len(self.plugin_inventory):self.message("Inspect the plugin first.");return
        args={"worker":self.paths["worker"].text(),"plugin":self.paths["plugin"].text(),"class_id":self.plugin_inventory[index]["class_id"],"presets":str(DATA/"presets")}
        if self.paths["state"].text():args["state"]=self.paths["state"].text()
        if self.parameters:args["parameters"]=self.parameters
        def edited(result):
            self.paths["state"].setText(result["state"]);self.parameters={};self.loading=True
            for row,parameter in enumerate(self.plugin_inventory[index]["parameters"]):
                value=result["parameter_values"].get(str(parameter["id"]),parameter["normalized"]);parameter["normalized"]=value;self.parameter_table.item(row,1).setText(str(value))
            self.loading=False;self.message("Plugin state saved for the next render.")
        self.request("plugins.edit" if interactive else "plugins.state.save",args,edited)
    def start_continuous(self):
        args={"bpm":self.bpm.value(),"builtin":self.continuous_source.currentIndex()==0}
        if args['builtin']:
            args['intent']={'root':self.key.currentIndex(),'mode':self.scale.currentText()}
            if self.score:args['intent'].update(parts=sorted({note['part'] for note in self.score['notes']}),seed=self.score.get('seed',0))
        if args["builtin"] and self.instruments:
            if not self.paths["worker"].text():self.message("Choose the host engine for assigned instruments.");return
            args.update(instruments=self.instruments,worker=self.paths["worker"].text())
        if not args["builtin"]:
            sample=self.sample()
            if not sample:self.message("Select a library sample first.");return
            args.update(catalog=self.paths["catalog"].text(),sample=sample["name"])
        if self.continuous_effect.isChecked():
            if not self.paths["plugin"].text() or not self.paths["worker"].text():self.message("Choose an effect and host engine first.");return
            args.update(self.processing())
            args['effect_output_bus']=self.continuous_effect_bus.value()
        self.request("continuous.play",args,lambda result:self.message("Disposable playback ended; temporary audio cleared."))
    def refresh_instruments(self):
        self.instrument_table.setRowCount(3)
        for row,part in enumerate(("bass","chords","melody")):
            spec=self.instruments.get(part)
            self.instrument_table.setItem(row,0,QTableWidgetItem(part.title()))
            value=QTableWidgetItem("VST3 · "+Path(spec["plugin"]).stem if spec else "Built-in")
            if spec:value.setToolTip(spec["class_id"]+"\n"+spec["plugin"])
            self.instrument_table.setItem(row,1,value)
    def clear_instrument(self):
        row=self.instrument_table.currentRow()
        if 0<=row<3:self.instruments.pop(("bass","chords","melody")[row],None);self.refresh_instruments()
    def assign_instrument(self):
        if self.busy:self.message("Wait for the active job first.");return
        dialog=QDialog(self);dialog.setWindowTitle("Assign a VST3 instrument");dialog.resize(640,350);form=QFormLayout(dialog)
        part=QComboBox();part.addItems(["bass","chords","melody"]);form.addRow("Part",part)
        path=QLineEdit();path.setAccessibleName("Instrument plugin path");row=QHBoxLayout();row.addWidget(path,1)
        def choose_file():
            chosen=QFileDialog.getOpenFileName(dialog,"VST3 binary",str(DATA),"VST3 (*.vst3)")[0]
            if chosen:path.setText(chosen)
        def choose_bundle():
            chosen=QFileDialog.getExistingDirectory(dialog,"VST3 bundle directory")
            if chosen:path.setText(chosen)
        row.addWidget(button("File…",choose_file));row.addWidget(button("Bundle…",choose_bundle));form.addRow("Plugin",row)
        classes=QComboBox();classes.setAccessibleName("Instrument component");form.addRow("Component",classes)
        routes=QLineEdit("0");routes.setAccessibleName("Instrument output bus numbers");form.addRow("Output buses",routes)
        message=QLabel("Inspect a user-installed plugin, then choose its instrument component. Output bus numbers are zero-based.");message.setWordWrap(True);form.addRow(message)
        available=[]
        def scanned(report):
            available[:]=[item for item in report["classes"] if item["audio_inputs"]==0 and item["audio_outputs"]>0]
            classes.clear();classes.addItems([f"{item['name']} · {item['audio_outputs']} outputs" for item in available])
            message.setText("Choose the part, component and desired output buses, then assign." if available else "No supported instrument component was found.")
        form.addRow(button("Inspect components",lambda:self.request("plugins.inspect",{"worker":self.paths["worker"].text(),"plugin":path.text()},scanned)))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);form.addRow(buttons)
        buttons.rejected.connect(dialog.reject)
        def accept():
            try:
                if not 0<=classes.currentIndex()<len(available):raise ValueError("Inspect and select an instrument first.")
                component=available[classes.currentIndex()];buses=[int(value.strip()) for value in routes.text().split(",")]
                if not buses or len(set(buses))!=len(buses) or any(not 0<=bus<component["audio_outputs"] for bus in buses):raise ValueError("Choose valid distinct output bus numbers.")
                self.instruments[part.currentText()]={"plugin":path.text(),"class_id":component["class_id"],"outputs":[{"bus":bus,"gain":1} for bus in buses]}
                self.refresh_instruments();dialog.accept();self.message("Instrument assigned. Rendering will preserve its component/controller state.")
            except ValueError as error:message.setText(str(error))
        buttons.accepted.connect(accept);dialog.exec()
    def edit_instrument(self):
        row=self.instrument_table.currentRow()
        if not 0<=row<3:self.message("Select a part first.");return
        part=("bass","chords","melody")[row];spec=self.instruments.get(part)
        if not spec:self.message("This part uses a built-in sound.");return
        args={"worker":self.paths["worker"].text(),"plugin":spec["plugin"],"class_id":spec["class_id"],"presets":str(DATA/"presets")}
        if spec.get("state"):args["state"]=spec["state"]
        def saved(result):spec["state"]=result["state"];self.message("Instrument preset saved and attached to this part.")
        self.request("plugins.edit",args,saved)
    def instrument_parameters(self):
        row=self.instrument_table.currentRow()
        if not 0<=row<3:self.message("Select an instrument part first.");return
        spec=self.instruments.get(("bass","chords","melody")[row])
        if not spec:self.message("Assign a VST3 instrument first.");return
        args={"worker":self.paths["worker"].text(),"plugin":spec["plugin"],"class_id":spec["class_id"]}
        if spec.get("state"):args["state"]=spec["state"]
        def saved(result):spec['state']=result['state'];self.message('Instrument program/parameter state captured and attached to this part.')
        self.edit_parameter_state(args,'Instrument parameters / programs',saved)
    def effect_parameter_dialog(self):
        processing=self.processing();class_id=processing.get('class_id')
        if not processing.get('plugin') or not class_id:self.message('Choose and inspect an effect component first.');return
        args={key:processing[key] for key in ('worker','plugin','class_id','state') if key in processing}
        def saved(result):
            self.paths['state'].setText(result['state']);self.restore_effect_selection(class_id,{})
            self.message('Effect program/parameter state captured. Inspect again to refresh its controls.')
        self.edit_parameter_state(args,'Effect parameters / programs',saved,self.parameters)
    def edit_parameter_state(self,args,title,saved,overrides=None):
        if self.busy:self.message('Wait for the active operation before editing plugin state.');return
        def inspected(result):
            if len(result['classes'])!=1:self.message('The plugin component is unavailable.');return
            from plugin_controls import ParameterDialog
            dialog=ParameterDialog(self,result['classes'][0],args,title)
            for row,value in enumerate(dialog.values):
                if str(value['id']) in (overrides or {}):dialog.table.item(row,1).setText(str(overrides[str(value['id'])]))
            if dialog.exec()==QDialog.DialogCode.Accepted:
                self.request('plugins.state.save',{**args,'presets':str(DATA/'presets'),'parameters':dialog.edits()},saved)
        self.request('plugins.inspect',args,inspected)
    def cancel(self):
        self.stop_preview()
        for process,marker,path in self.tasks:
            marker.touch()
            if process not in self.cancel_deadlines:
                self.cancel_deadlines.add(process)
                QTimer.singleShot(6000,lambda process=process,marker=marker:self.force_canceled(process,marker))
        if self.tasks:self.message("Canceling the active job and its child processes…")
    def force_canceled(self,process,marker):
        if not marker.exists() or not any(task[0] is process for task in self.tasks):return
        guard=self.command_guards.get(process)
        if guard:
            try:guard.terminate()
            except OSError as error:self.message('Could not stop the verified command: '+str(error));return
        self.forced_cancellations.add(process)
        # The verified actual command owns the child job. Kill its Qt launcher
        # too, if still present, so source Python launchers cannot hold UI open.
        process.kill()
    def closeEvent(self,event):
        self.cancel()
        self.stop_preview()
        if self.tasks:
            self.closing=True;event.ignore();self.message('Stopping owned work before closing…');return
        self.persist_draft()
        if self.temporary_session:
            try:self.temporary_session.close()
            except (OSError,ValueError) as error:event.ignore();self.message('Temporary result cleanup incomplete: '+str(error));return
        for path in self.owned_snapshots:path.unlink(missing_ok=True)
        settings={key:edit.text() for key,edit in self.paths.items() if key!='voice'};settings['keep_recovery']=self.keep_recovery.isChecked()
        self.settings.write_text(json.dumps(settings,indent=2),encoding='utf-8');self.draft_timer.stop();event.accept()


def main():
    app=QApplication(sys.argv);app.setApplicationName("Sample Arranger");app.setStyle("Fusion");app.setStyleSheet(STYLE)
    window=Workspace();icon=resource('arranger.png')
    if not icon.exists():icon=resource('arranger.svg')
    window.setWindowIcon(QIcon(str(icon)));window.show();sys.exit(app.exec())


if __name__=="__main__":main()
