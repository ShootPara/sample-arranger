"""Desktop controls for the local catalog and render commands."""
import json
import os
import queue
import sqlite3
import subprocess
import sys
import threading
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from commands import execute
from audio_tools import file_inputs


def main():
    window = tk.Tk()
    window.title("Sample Arranger")
    window.geometry("1440x840")
    window.minsize(1180, 760)
    window.configure(bg="#131b24")
    style = ttk.Style(window)
    style.theme_use("clam")
    style.configure(".", background="#18232f", foreground="#e4edf4", font=("Segoe UI", 11))
    style.configure("TEntry", fieldbackground="#263646", foreground="#ffffff", insertcolor="white")
    style.configure("TButton", padding=(14, 8), background="#276d72")
    style.configure("Treeview", background="#1c2b39", fieldbackground="#1c2b39",
                    foreground="#e4edf4", rowheight=30)
    style.map("TNotebook.Tab",background=[("selected","#276d72"),("!selected","#263646")],
              foreground=[("selected","#ffffff"),("!selected","#d5e3eb")])
    style.map("TCombobox",fieldbackground=[("readonly","#263646")],foreground=[("readonly","#ffffff")])
    style.map("TButton", foreground=[("disabled", "#8b9ca9"), ("active", "#ffffff")],
              background=[("active", "#35868c"), ("disabled", "#263646")])
    workspace = ttk.Panedwindow(window, orient="horizontal")
    workspace.pack(fill="both", expand=True, padx=12, pady=12)
    library = ttk.Frame(workspace, padding=12)
    center = ttk.Frame(workspace, padding=12)
    panel = ttk.Frame(workspace, padding=16)
    workspace.add(library, weight=2)
    workspace.add(center, weight=3)
    workspace.add(panel, weight=2)
    ttk.Label(library, text="LIBRARY", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    ttk.Label(library, text="Choose a catalog in the inspector.").pack(anchor="w", pady=8)
    sample_list = ttk.Treeview(library, columns=("duration",), show="tree headings", height=18)
    sample_list.heading("#0", text="Sample")
    sample_list.heading("duration", text="Seconds")
    sample_list.column("#0", width=210)
    sample_list.column("duration", width=65)
    sample_list.pack(fill="both", expand=True)
    ttk.Label(center, text="ARRANGEMENT", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    ttk.Label(center, text="Describe the music and duration").pack(anchor="w", pady=(8, 2))
    brief = ttk.Entry(center)
    brief.pack(fill="x")
    advanced_plan = tk.BooleanVar(value=False)
    plan_header = ttk.Frame(center)
    plan_header.pack(fill="x",pady=8)
    ttk.Label(plan_header, text="Section plan",font=("Segoe UI",11,"bold")).pack(side="left")
    editor = tk.Text(center, height=7, bg="#263646", fg="#ffffff", insertbackground="white",
                     font=("Consolas", 10), wrap="word")
    def toggle_plan():
        if advanced_plan.get():editor.pack(fill="x",pady=4,before=timeline)
        else:editor.pack_forget()
    ttk.Checkbutton(plan_header,text="Advanced JSON",variable=advanced_plan,
                    command=toggle_plan).pack(side="right")
    timeline = tk.Canvas(center, bg="#101923", highlightthickness=0, height=260)
    timeline.pack(fill="both", expand=True)
    transport_label=ttk.Label(center, text="Transport", font=("Segoe UI", 12, "bold"))
    transport_label.pack(anchor="w", pady=(18, 4))
    panel.columnconfigure(1, weight=1)
    ttk.Label(panel, text="INSPECTOR", font=("Segoe UI", 14, "bold")).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 16)
    )
    fields = {}
    inspector_tabs=ttk.Notebook(panel)
    inspector_tabs.grid(row=1,column=0,columnspan=3,sticky="nsew")
    project_tab=ttk.Frame(inspector_tabs,padding=10)
    plugins_tab=ttk.Frame(inspector_tabs,padding=10)
    inspector_tabs.add(project_tab,text="Project")
    inspector_tabs.add(plugins_tab,text="Plugins")
    for tab in (project_tab,plugins_tab):tab.columnconfigure(1,weight=1)
    field_rows={project_tab:0,plugins_tab:0}
    for row, (name, label, chooser) in enumerate([
        ("catalog", "Catalog", filedialog.askopenfilename),
        ("search", "Find samples", None),
        ("seconds", "Duration (seconds)", None),
        ("voice", "Narration (optional)", filedialog.askopenfilename),
        ("jobs", "Output folder", filedialog.askdirectory),
        ("worker", "Host engine", filedialog.askopenfilename),
        ("plugin", "Effect", filedialog.askopenfilename),
        ("state", "Preset state", filedialog.askopenfilename),
    ], 1):
        value = fields[name] = tk.StringVar(value="30" if name == "seconds" else "")
        container=plugins_tab if name in ("worker","plugin","state") else project_tab
        row=field_rows[container]
        field_rows[container]+=1
        ttk.Label(container, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=8)
        ttk.Entry(container, textvariable=value,width=20).grid(row=row, column=1, sticky="ew")
        if chooser:
            def choose(dialog=chooser, field=value):
                selected = dialog(parent=window)
                if selected:
                    field.set(selected)
            ttk.Button(container, text="Browse…", command=choose).grid(row=row, column=2, padx=(8, 0))

    status = tk.StringVar(value="Choose a catalog and output folder to begin.")
    ttk.Label(panel, textvariable=status, wraplength=580).grid(
        row=11, column=0, columnspan=3, sticky="w", pady=(12, 0)
    )
    results = queue.Queue()
    running = []
    output = []
    previews = []
    canceled = threading.Event()
    cancel_marker = []
    refinement = []
    project_file = []
    project_revision = [0]
    selected_section = [0]
    plugin_values = {}
    plugin_choice = []
    auxiliary = []
    progress = ttk.Progressbar(panel, mode="indeterminate")
    progress.grid(row=10, column=0, columnspan=3, sticky="ew", pady=12)

    def run(command, temporary_paths):
        try:
            environment = dict(os.environ)
            if cancel_marker:
                environment["ARRANGER_CANCEL_FILE"] = str(cancel_marker[0])
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  env=environment,
                                  errors="replace", creationflags=subprocess.CREATE_NO_WINDOW) as process:
                running.append(process)
                if canceled.is_set():
                    cancel_marker[0].touch()
                stdout, stderr = process.communicate()
                payload = json.loads(stdout) if stdout.strip() else {}
                result = payload["result"]["audio"] if process.returncode == 0 else payload.get("error",{}).get("message",stderr.strip())
                if process.returncode == 0:
                    output[:] = [result]
                running.clear()
            if canceled.is_set():
                result = "Render canceled."
            results.put(result)
        except (OSError, ValueError, KeyError) as error:
            results.put(str(error))
        finally:
            if cancel_marker:
                cancel_marker[0].unlink(missing_ok=True)
            for path in temporary_paths:
                Path(path).unlink(missing_ok=True)
            running.clear()

    def poll():
        try:
            status.set(results.get_nowait())
        except queue.Empty:
            window.after(100, poll)
            return
        button.state(["!disabled"])
        progress.stop()

    def cancel():
        canceled.set()
        if cancel_marker:
            cancel_marker[0].touch()

    def submit():
        if running or button.instate(["disabled"]):
            return
        values = {key: value.get() for key, value in fields.items()}
        if not values["catalog"] or not values["jobs"]:
            status.set("Choose a catalog and output folder.")
            return
        edited = editor.get("1.0", "end").strip()
        temporary_paths=[]
        try:
            from render import resolve_sections
            from planner import local_sections
            sections = json.loads(edited) if edited else local_sections(Path(values["catalog"]),values["search"],float(values["seconds"]))
            resolve_sections(sections,Path(values["catalog"]))
            arguments={key:value for key,value in values.items() if key not in ("search","seconds") and value}
            arguments["sections"]=sections
            if plugin_choice and plugin_choice[0]==values["plugin"]:
                arguments["class_id"]=plugin_choice[1]
                if plugin_values:
                    descriptor,path=tempfile.mkstemp(suffix=".txt",prefix="arranger-automation-")
                    temporary_paths.append(path)
                    with os.fdopen(descriptor,"w",encoding="utf-8") as saved:
                        saved.write("".join(f"0 {key} {value}\n" for key,value in sorted(plugin_values.items())))
                    arguments["automation"]=path
            descriptor,path=tempfile.mkstemp(suffix=".json",prefix="arranger-request-")
            temporary_paths.append(path)
            with os.fdopen(descriptor,"w",encoding="utf-8") as saved:
                json.dump({"contract":1,"operation":"arrangement.render","arguments":arguments},saved)
        except (ValueError,OSError,sqlite3.Error) as error:
            for path in temporary_paths:Path(path).unlink(missing_ok=True)
            status.set(str(error))
            return
        command=[sys.executable,"-B",str(Path(__file__).with_name("commands.py")),"--request",path]
        canceled.clear()
        import uuid
        cancel_marker[:] = [Path(tempfile.gettempdir()) / f"arranger-cancel-{uuid.uuid4()}"]
        button.state(["disabled"])
        progress.start()
        status.set("Rendering…")
        threading.Thread(target=run, args=(command,temporary_paths), daemon=True).start()
        window.after(100, poll)

    def create_plan():
        text = brief.get()
        try:
            arguments={"catalog":fields["catalog"].get(),"initial":refinement[0] if refinement else text}
            if refinement:arguments["refined"]=text
            result=execute({"contract":1,"operation":"brief.plan","arguments":arguments})["result"]
            if result["state"] != "ready":
                if not refinement and result["state"] == "needs_input":
                    refinement.append(text)
                status.set(result["message"])
                return
            editor.delete("1.0", "end")
            editor.insert("1.0", json.dumps(result["sections"], indent=2))
            refresh_timeline()
            status.set("Plan ready. Edit section order, sample names or durations, then render.")
        except (ValueError, OSError, sqlite3.Error) as error:
            status.set(str(error))
    actions = ttk.Frame(center)
    actions.pack(fill="x", pady=6,before=plan_header)
    ttk.Button(actions, text="Plan from brief", command=create_plan).pack(side="left")
    def new_brief():
        refinement.clear()
        status.set("New brief. Enter the music and duration, then choose Plan from brief.")
    ttk.Button(actions, text="New brief", command=new_brief).pack(side="left", padx=6)

    # Timeline and accessible non-drag editing share the exact JSON section model.
    section_controls = ttk.Frame(center)
    section_controls.pack(fill="x", pady=4,before=transport_label)
    section_seconds = tk.StringVar(value="4")
    ttk.Label(section_controls, text="Section seconds").pack(side="left")
    length_entry = ttk.Entry(section_controls, textvariable=section_seconds, width=6)
    length_entry.pack(side="left", padx=4)

    def current_sections():
        sections = json.loads(editor.get("1.0", "end"))
        if not isinstance(sections, list) or not 1 <= len(sections) <= 16:
            raise ValueError("Use one to sixteen sections.")
        from render import resolve_sections
        resolve_sections(sections, Path(fields["catalog"].get()))
        return sections

    def refresh_timeline(event=None):
        timeline.delete("all")
        try:
            sections = current_sections()
            total = sum(section["seconds"] for section in sections)
            width = max(300, timeline.winfo_width()) - 32
            timeline.create_text(16, 22, anchor="w", fill="#c8d8e6", text=f"SAMPLE TRACK  /  {total:g} seconds")
            x = 16
            for index, section in enumerate(sections):
                end = x + width * section["seconds"] / total
                color = "#35868c" if index == selected_section[0] else "#264e65"
                tag = f"section-{index}"
                timeline.create_rectangle(x, 45, end-2, 130, fill=color, outline="#88ced2", tags=tag)
                timeline.create_text(x+6, 63, anchor="nw", fill="white", width=max(30,end-x-12),
                                     text=f"{index+1}. {section['sample']}\n{section['seconds']:g}s", tags=tag)
                timeline.tag_bind(tag, "<Button-1>", lambda event, i=index: select_section(i))
                x = end
        except (ValueError, OSError, sqlite3.Error):
            timeline.create_text(20, 40, anchor="w", fill="#c8d8e6", text="Build a plan or choose a sample to begin.")

    def select_section(index):
        try:
            sections = current_sections()
            selected_section[0] = max(0, min(index, len(sections)-1))
            section_seconds.set(str(sections[selected_section[0]]["seconds"]))
            refresh_timeline()
        except (ValueError, OSError, sqlite3.Error) as error:
            status.set(str(error))

    def edit_section(action):
        try:
            sections = current_sections()
            index = min(selected_section[0],len(sections)-1)
            if action == "length":
                sections[index]["seconds"] = float(section_seconds.get())
            elif action == "remove":
                if len(sections) == 1:
                    raise ValueError("Keep at least one section.")
                sections.pop(index)
                selected_section[0] = max(0,index-1)
            else:
                other = index + action
                if 0 <= other < len(sections):
                    sections[index], sections[other] = sections[other], sections[index]
                    selected_section[0] = other
            from render import resolve_sections
            resolve_sections(sections,Path(fields["catalog"].get()))
            if sum(section["seconds"] for section in sections) > 240:
                raise ValueError("Normal arrangements are limited to four minutes.")
            editor.delete("1.0","end")
            editor.insert("1.0",json.dumps(sections,indent=2))
            refresh_timeline()
            status.set("Arrangement updated. Render to hear the change.")
        except (ValueError, OSError, sqlite3.Error) as error:
            status.set(str(error))

    for label, action in (("Apply", "length"),("←",-1),("→",1),("Remove","remove")):
        ttk.Button(section_controls,text=label,command=lambda a=action: edit_section(a)).pack(side="left",padx=2)
    length_entry.bind("<Return>",lambda event: edit_section("length"))
    timeline.bind("<Configure>",refresh_timeline)
    editor.bind("<FocusOut>",refresh_timeline)

    project_controls = ttk.Frame(center)
    project_controls.pack(fill="x",pady=4,before=transport_label)
    def save_project():
        try:
            from project import save
            destination = project_file[0] if project_file else filedialog.asksaveasfilename(
                parent=window,defaultextension=".json",filetypes=[("Arranger project","*.json")])
            if not destination:
                return
            result = save(Path(destination),current_sections(),Path(fields["catalog"].get()),
                          expected_revision=project_revision[0],brief={"effective":brief.get(),
                          "initial":refinement[0] if refinement else brief.get()},
                          processing={key:fields[key].get() for key in ("worker","plugin","state") if fields[key].get()})
            project_file[:] = [destination]
            project_revision[0] = result["revision"]
            status.set(f"Project saved · revision {result['revision']}")
        except (ValueError,OSError,sqlite3.Error) as error:
            status.set(str(error))
    def open_project():
        destination = filedialog.askopenfilename(parent=window,filetypes=[("Arranger project","*.json")])
        if not destination:
            return
        try:
            from project import inspect
            result = inspect(Path(destination))
            if not result["ready"]:
                raise ValueError("Project needs asset recovery: "+json.dumps(result["issues"]))
            project = result["project"]
            from project import pinned_sections
            pinned_sections(Path(destination))
            fields["catalog"].set(project["catalog"])
            for key in ("worker","plugin","state"):
                fields[key].set(project.get("processing",{}).get(key,{}).get("path",""))
            editor.delete("1.0","end")
            editor.insert("1.0",json.dumps(project["sections"],indent=2))
            project_file[:] = [destination]
            project_revision[0] = project["revision"]
            selected_section[0] = 0
            refinement.clear()
            if project.get("brief"):
                brief.delete(0,"end")
                brief.insert(0,project["brief"].get("effective",""))
            refresh_timeline()
            select_section(0)
            status.set(f"Project opened · revision {project['revision']}")
        except (ValueError,OSError) as error:
            status.set(str(error))
    ttk.Button(project_controls,text="Save project",command=save_project).pack(side="left")
    ttk.Button(project_controls,text="Open project",command=open_project).pack(side="left",padx=6)
    window.bind("<Control-s>",lambda event: save_project())
    window.bind("<Control-o>",lambda event: open_project())

    button = ttk.Button(panel, text="Render MP3", command=submit)
    button.grid(row=9, column=1, sticky="e", pady=(14, 0))
    ttk.Button(panel, text="Cancel", command=cancel).grid(row=9, column=0, sticky="w")
    def plugin_controls():
        worker,plugin=fields["worker"].get(),fields["plugin"].get()
        if not worker or not plugin:
            status.set("Choose the VST3 worker and effect, then open Plugin controls.")
            return
        rack=tk.Toplevel(window)
        rack.title("Plugin controls · Sample Arranger")
        rack.geometry("720x520")
        rack.configure(bg="#18232f")
        rack.columnconfigure(0,weight=1)
        rack.rowconfigure(2,weight=1)
        message=tk.StringVar(value="Inspecting the plugin in an isolated process…")
        ttk.Label(rack,textvariable=message,wraplength=680).grid(row=0,column=0,sticky="ew",padx=16,pady=12)
        classes=ttk.Combobox(rack,state="readonly")
        classes.grid(row=1,column=0,sticky="ew",padx=16)
        parameters=ttk.Treeview(rack,columns=("value","units"),show="tree headings")
        parameters.heading("#0",text="Parameter")
        parameters.heading("value",text="Normalized value")
        parameters.heading("units",text="Units")
        parameters.column("#0",width=330)
        parameters.column("value",width=120)
        parameters.column("units",width=100)
        parameters.grid(row=2,column=0,sticky="nsew",padx=16,pady=12)
        controls=ttk.Frame(rack)
        controls.grid(row=3,column=0,sticky="ew",padx=16,pady=12)
        ttk.Label(controls,text="Value (0–1)").pack(side="left")
        normalized=tk.StringVar(value="0.5")
        ttk.Entry(controls,textvariable=normalized,width=8).pack(side="left",padx=6)
        inventory=[]
        metadata={}
        def choose_class(event=None):
            if classes.current()<0:return
            chosen=inventory[classes.current()]
            plugin_values.clear()
            plugin_choice[:]=[plugin,chosen["class_id"]]
            parameters.delete(*parameters.get_children())
            metadata.clear()
            for parameter in chosen["parameters"]:
                item=parameters.insert("","end",text=parameter["name"],values=(parameter["normalized"],parameter["units"]))
                metadata[item]=parameter
            message.set(f"{chosen['name']} · {chosen['version']} · {len(metadata)} parameters. Edits apply on the next render.")
        classes.bind("<<ComboboxSelected>>",choose_class)
        def select_parameter(event=None):
            selection=parameters.selection()
            if selection:normalized.set(str(plugin_values.get(metadata[selection[0]]["id"],metadata[selection[0]]["normalized"])))
        parameters.bind("<<TreeviewSelect>>",select_parameter)
        def apply_parameter():
            try:
                import math
                selection=parameters.selection()
                if not selection:raise ValueError("Select a parameter first.")
                parameter=metadata[selection[0]]
                value=float(normalized.get())
                if not math.isfinite(value) or not 0<=value<=1:raise ValueError("Use a value between zero and one.")
                if parameter["flags"]&2:raise ValueError("This parameter is read-only.")
                plugin_values[parameter["id"]]=value
                parameters.set(selection[0],"value",value)
                message.set("Parameter queued for the next render. Source preset remains unchanged.")
            except ValueError as error:message.set(str(error))
        ttk.Button(controls,text="Apply parameter",command=apply_parameter).pack(side="left",padx=4)
        def request_background(operation,arguments,on_success):
            import uuid
            marker=Path(tempfile.gettempdir())/f"arranger-plugin-cancel-{uuid.uuid4()}"
            auxiliary.append(marker)
            delivered=queue.Queue()
            def task():
                descriptor,path=tempfile.mkstemp(prefix="arranger-plugin-request-",suffix=".json")
                try:
                    with os.fdopen(descriptor,"w",encoding="utf-8") as source:
                        json.dump({"contract":1,"operation":operation,"arguments":arguments},source)
                    result=subprocess.run([sys.executable,"-B",str(Path(__file__).with_name("commands.py")),"--request",path],
                        capture_output=True,text=True,env=dict(os.environ,ARRANGER_CANCEL_FILE=str(marker)),
                        creationflags=subprocess.CREATE_NO_WINDOW)
                    payload=json.loads(result.stdout)
                    delivered.put((result.returncode,payload))
                except (ValueError,OSError) as error:delivered.put((1,{"error":{"message":str(error)}}))
                finally:
                    Path(path).unlink(missing_ok=True)
                    marker.unlink(missing_ok=True)
                    if marker in auxiliary:auxiliary.remove(marker)
            def receive():
                try:code,payload=delivered.get_nowait()
                except queue.Empty:
                    if rack.winfo_exists():rack.after(100,receive)
                    return
                if not rack.winfo_exists():return
                if code:message.set(payload.get("error",{}).get("message","Plugin operation failed."))
                else:on_success(payload["result"])
            threading.Thread(target=task,daemon=True).start()
            rack.after(100,receive)
        def loaded(report):
            inventory[:]=report["classes"]
            classes["values"]=[item["name"] for item in inventory]
            if inventory:classes.current(0);choose_class()
            else:message.set("No audio classes found in this plugin.")
        def open_native():
            if not plugin_choice:return
            arguments={"worker":worker,"plugin":plugin,"class_id":plugin_choice[1],
                       "presets":str(Path(os.environ["LOCALAPPDATA"],"SampleArranger/presets"))}
            if fields["state"].get():arguments["state"]=fields["state"].get()
            if plugin_values:arguments["parameters"]={str(key):value for key,value in plugin_values.items()}
            message.set("Native editor is open in its own process. Close it to save a new local preset.")
            def edited(result):
                fields["state"].set(result["state"])
                plugin_values.clear()
                for item,parameter in metadata.items():
                    value=result["parameter_values"].get(str(parameter["id"]),parameter["normalized"])
                    parameter["normalized"]=value
                    parameters.set(item,"value",value)
                message.set("Editor state saved. Component and controller will restore on the next render.")
            request_background("plugins.edit",arguments,edited)
        ttk.Button(controls,text="Open native editor",command=open_native).pack(side="left",padx=4)
        def close_rack():
            for marker in auxiliary:marker.touch()
            rack.destroy()
        rack.protocol("WM_DELETE_WINDOW",close_rack)
        request_background("plugins.inspect",{"worker":worker,"plugin":plugin},loaded)
    ttk.Button(plugins_tab,text="Plugin controls…",command=plugin_controls).grid(row=4,column=0,columnspan=3,sticky="w",pady=12)
    def preview():
        if output:
            previews.append(subprocess.Popen(file_inputs(["ffplay", "-nodisp", "-autoexit", output[-1]]),
                                            creationflags=subprocess.CREATE_NO_WINDOW))
    ttk.Button(center, text="Play render", command=preview).pack(side="left", pady=8)
    def stop_preview():
        for process in previews:
            if process.poll() is None:
                process.terminate()
        previews.clear()
    ttk.Button(center, text="Stop", command=stop_preview).pack(side="left", padx=8)
    available = {}

    def refresh_library():
        sample_list.delete(*sample_list.get_children())
        available.clear()
        try:
            connection = sqlite3.connect(Path(fields["catalog"].get()).resolve().as_uri() + "?mode=ro", uri=True)
            try:
                rows = connection.execute("SELECT path, name, seconds FROM sample ORDER BY name LIMIT 200").fetchall()
            finally:
                connection.close()
            for path, name, duration in rows:
                item = sample_list.insert("", "end", text=name,
                                          values=(f"{duration:.2f}" if duration else "—",))
                available[item] = path
        except (OSError, sqlite3.Error) as error:
            status.set(str(error))

    def select_sample(event=None):
        selected = sample_list.selection()
        if selected:
            path = available[selected[0]]
            fields["search"].set(Path(path).name)
            editor.delete("1.0", "end")
            editor.insert("1.0", json.dumps([{"sample": Path(path).name,
                                             "seconds": float(fields["seconds"].get())}], indent=2))
            refresh_timeline()
    sample_list.bind("<<TreeviewSelect>>", select_sample)
    def audition():
        selected = sample_list.selection()
        if selected:
            stop_preview()
            previews.append(subprocess.Popen(file_inputs(["ffplay", "-nodisp", "-autoexit", "-t", "10",
                                             available[selected[0]]]),
                                            creationflags=subprocess.CREATE_NO_WINDOW))
    ttk.Button(library, text="Load catalog", command=refresh_library).pack(side="left", pady=12)
    ttk.Button(library, text="Audition", command=audition).pack(side="left", padx=8)
    sample_list.bind("<space>", lambda event: audition())
    window.bind("<Control-Return>", lambda event: submit())
    window.bind("<Escape>", lambda event: (cancel(), stop_preview()))
    def close():
        cancel()
        for marker in auxiliary:marker.touch()
        stop_preview()
        window.destroy()
    window.protocol("WM_DELETE_WINDOW", close)
    window.mainloop()


if __name__ == "__main__":
    main()
