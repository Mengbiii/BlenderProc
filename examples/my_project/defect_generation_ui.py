"""Desktop UI for the defect dataset generator.

The UI is intentionally a thin, safe wrapper around defect_dataset_generator/app.py.
It reads the existing target profiles, builds real CLI commands, streams logs,
and previews generated RGB/mask images from an isolated output folder.
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk

try:
    from PIL import Image, ImageTk
except Exception:  # Pillow is optional; Tk can still run without previews.
    Image = None
    ImageTk = None


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
APP_PATH = REPO_ROOT / "defect_dataset_generator" / "app.py"
PROFILE_PATH = REPO_ROOT / "defect_dataset_generator" / "config" / "model_color_profiles.json"
TARGETS_PATH = REPO_ROOT / "defect_dataset_generator" / "config" / "model_color_defect_targets.json"
GENERATION_DEFAULTS_PATH = REPO_ROOT / "defect_dataset_generator" / "config" / "generation_defaults_registry.json"
BLACK_DOT_PRESETS_PATH = REPO_ROOT / "defect_dataset_generator" / "config" / "black_dot_appearance_presets.json"
DEFAULT_PYTHON = Path(r"D:\Anaconda\envs\defect_eval\python.exe")

APPROVED_COOCCURRENCE = {
    "qc71336_gray": [("black_dot", "mixed_color_contamination")],
    "qc71336_black": [("foreign_material", "splay")],
    "qc7_5244_black": [
        ("black_dot", "foreign_material"),
        ("black_dot", "splay"),
        ("foreign_material", "splay"),
        ("black_dot", "foreign_material", "splay"),
    ],
}

TEXT = {
    "en": {
        "title": "Defect Dataset Generator",
        "run_setup": "Run Setup",
        "command_log": "Command and Log",
        "result_preview": "Result Preview",
        "python": "Python",
        "browse": "Browse",
        "language": "Language",
        "target": "Target",
        "mode": "Mode",
        "single": "Single",
        "cooccurrence": "Cooccurrence",
        "normal": "Normal",
        "defects": "Defects",
        "defect_params": "Defect Parameters",
        "use_custom_params": "Use custom parameters",
        "reset_params": "Reset to defaults",
        "no_params": "No editable parameters for this backend.",
        "normal_params": "Normal generation has no defect parameters.",
        "co_combo": "Approved cooccurrence combo",
        "no_combo": "No approved cooccurrence combo for this target",
        "side": "Side",
        "count": "Count",
        "defect_count_max": "Max Defects",
        "samples": "Samples",
        "seed": "Seed",
        "output": "Output Folder",
        "auto_output": "Auto output path",
        "dry_run": "Dry run only",
        "dry_run_help": "Dry run means only writing/previewing the generation plan and command. It does not launch Blender rendering.",
        "large": "Allow count > 20 from UI",
        "refresh": "Refresh Command",
        "run": "Run",
        "stop": "Stop",
        "command_preview": "Command Preview",
        "copy": "Copy Command",
        "load": "Load Results",
        "open": "Open Output",
        "view": "View",
        "prev": "Prev",
        "next": "Next",
        "no_image": "No image loaded",
        "dry_run_no_image": "Dry run completed. No RGB/mask images were rendered.",
        "ready": "Ready",
    },
    "zh": {
        "title": "缺陷数据集生成器",
        "run_setup": "运行设置",
        "command_log": "命令与日志",
        "result_preview": "结果预览",
        "python": "Python 环境",
        "browse": "浏览",
        "language": "语言",
        "target": "目标",
        "mode": "模式",
        "single": "单缺陷",
        "cooccurrence": "同场景多缺陷",
        "normal": "正常样本",
        "defects": "缺陷",
        "defect_params": "缺陷参数",
        "use_custom_params": "使用自定义参数",
        "reset_params": "恢复默认值",
        "no_params": "当前后端没有可编辑参数。",
        "normal_params": "正常样本不需要缺陷参数。",
        "co_combo": "已确认可用的同场景组合",
        "no_combo": "该目标当前没有已确认的同场景组合",
        "side": "生成面",
        "count": "数量",
        "samples": "采样",
        "seed": "种子",
        "output": "输出目录",
        "auto_output": "自动输出路径",
        "dry_run": "仅演练",
        "dry_run_help": "Dry run/仅演练：只写入和预览生成计划及命令，不启动 Blender 渲染，也不会生成真实 RGB/mask。",
        "large": "允许 UI 运行数量 > 20",
        "refresh": "刷新命令",
        "run": "运行",
        "stop": "停止",
        "command_preview": "命令预览",
        "copy": "复制命令",
        "load": "加载结果",
        "open": "打开输出目录",
        "view": "视图",
        "prev": "上一张",
        "next": "下一张",
        "no_image": "未加载图像",
        "dry_run_no_image": "仅演练已完成，未渲染 RGB/mask 图像。",
        "ready": "就绪",
    },
}


class DefectGenerationUI:
    def __init__(self, master):
        self.master = master
        self.master.title(self.tr("title"))
        self.master.geometry("1320x860")
        self.master.minsize(1180, 760)

        self.profiles = self.load_profiles()
        self.targets = self.load_targets()
        self.generation_defaults = self.load_json_file(GENERATION_DEFAULTS_PATH)
        self.black_dot_presets = self.load_json_file(BLACK_DOT_PRESETS_PATH)
        self.process = None
        self.log_queue = queue.Queue()
        self.preview_files = []
        self.preview_index = 0
        self.preview_image = None
        self.text_widgets = {}

        self.build_variables()
        self.build_layout()
        self.refresh_target_details()
        self.refresh_command_preview()
        self.poll_log_queue()

    def load_profiles(self):
        with PROFILE_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle).get("profiles", {})

    def load_targets(self):
        if not TARGETS_PATH.exists():
            return {}
        with TARGETS_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle).get("targets", {})

    def load_json_file(self, path):
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def build_variables(self):
        targets = sorted(self.profiles)
        self.target_var = tk.StringVar(value=targets[0] if targets else "")
        self.mode_var = tk.StringVar(value="single")
        self.side_var = tk.StringVar(value="front")
        self.count_var = tk.IntVar(value=1)
        self.defect_count_max_var = tk.IntVar(value=1)
        self.samples_var = tk.IntVar(value=16)
        self.seed_var = tk.IntVar(value=90001)
        self.dry_run_var = tk.BooleanVar(value=True)
        self.allow_large_var = tk.BooleanVar(value=False)
        self.python_var = tk.StringVar(value=str(DEFAULT_PYTHON if DEFAULT_PYTHON.exists() else Path(sys.executable)))
        self.output_is_auto = True
        self.output_run_stamp = self.current_run_stamp()
        default_out = self.make_default_output_dir()
        self.last_auto_output = str(default_out)
        self.output_var = tk.StringVar(value=str(default_out))
        self.command_var = tk.StringVar(value="")
        self.lang_var = tk.StringVar(value="中文")
        self.status_var = tk.StringVar(value="就绪")
        self.preview_mode_var = tk.StringVar(value="rgb")
        self.defect_vars = {}
        self.selected_defect_var = tk.StringVar(value="")
        self.cooccurrence_var = tk.StringVar(value="")
        self.use_custom_params_var = tk.BooleanVar(value=False)
        self.param_vars = {}
        self.current_param_specs = {}

    def lang_key(self):
        if not hasattr(self, "lang_var"):
            return "zh"
        return "zh" if self.lang_var.get() == "中文" else "en"

    def tr(self, key):
        return TEXT[self.lang_key()].get(key, key)

    def build_layout(self):
        root = ttk.Frame(self.master, padding=10)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(root, text=self.tr("run_setup"), padding=0)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        center = ttk.LabelFrame(root, text=self.tr("command_log"), padding=10)
        center.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        center.rowconfigure(3, weight=1)
        center.columnconfigure(0, weight=1)
        right = ttk.LabelFrame(root, text=self.tr("result_preview"), padding=10)
        right.grid(row=0, column=2, sticky="nse")
        self.text_widgets["run_setup_frame"] = left
        self.text_widgets["command_log_frame"] = center
        self.text_widgets["result_preview_frame"] = right

        left_panel = self.build_scrollable_left_panel(left)
        self.build_left_panel(left_panel)
        self.build_center_panel(center)
        self.build_right_panel(right)

    def build_scrollable_left_panel(self, parent):
        canvas = tk.Canvas(parent, width=430, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        inner = ttk.Frame(canvas, padding=10)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def sync_inner_width(event):
            canvas.itemconfigure(window_id, width=event.width)

        def on_mousewheel(event):
            delta = event.delta
            if delta:
                canvas.yview_scroll(int(-1 * (delta / 120)), "units")

        inner.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", sync_inner_width)
        canvas.bind("<Enter>", lambda _event: canvas.bind_all("<MouseWheel>", on_mousewheel))
        canvas.bind("<Leave>", lambda _event: canvas.unbind_all("<MouseWheel>"))
        return inner

    def build_left_panel(self, parent):
        self.python_label = ttk.Label(parent, text=self.tr("python"))
        self.python_label.grid(row=0, column=0, sticky="w")
        python_row = ttk.Frame(parent)
        python_row.grid(row=1, column=0, sticky="ew", pady=(2, 8))
        python_row.columnconfigure(0, weight=1)
        ttk.Entry(python_row, textvariable=self.python_var, width=36).grid(row=0, column=0, sticky="ew")
        self.python_browse_button = ttk.Button(python_row, text=self.tr("browse"), command=self.browse_python)
        self.python_browse_button.grid(row=0, column=1, padx=(6, 0))

        lang_row = ttk.Frame(parent)
        lang_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.language_label = ttk.Label(lang_row, text=self.tr("language"))
        self.language_label.pack(side="left")
        self.language_combo = ttk.Combobox(lang_row, textvariable=self.lang_var, values=["中文", "English"], state="readonly", width=10)
        self.language_combo.pack(side="left", padx=(8, 0))
        self.language_combo.bind("<<ComboboxSelected>>", lambda _event: self.apply_language())

        self.target_label = ttk.Label(parent, text=self.tr("target"))
        self.target_label.grid(row=3, column=0, sticky="w")
        self.target_combo = ttk.Combobox(
            parent,
            textvariable=self.target_var,
            values=sorted(self.profiles),
            state="readonly",
            width=34,
        )
        self.target_combo.grid(row=4, column=0, sticky="ew", pady=(2, 8))
        self.target_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_target_details())

        self.mode_label = ttk.Label(parent, text=self.tr("mode"))
        self.mode_label.grid(row=5, column=0, sticky="w")
        mode_frame = ttk.Frame(parent)
        mode_frame.grid(row=6, column=0, sticky="ew", pady=(2, 8))
        self.mode_buttons = {}
        for value, key in (("single", "single"), ("cooccurrence", "cooccurrence"), ("normal", "normal")):
            btn = ttk.Radiobutton(mode_frame, text=self.tr(key), value=value, variable=self.mode_var, command=self.refresh_target_details)
            btn.pack(side="left")
            self.mode_buttons[key] = btn

        self.defects_label = ttk.Label(parent, text=self.tr("defects"))
        self.defects_label.grid(row=7, column=0, sticky="w")
        self.defects_frame = ttk.Frame(parent)
        self.defects_frame.grid(row=8, column=0, sticky="ew", pady=(2, 8))

        self.params_frame = ttk.LabelFrame(parent, text=self.tr("defect_params"), padding=8)
        self.params_frame.grid(row=9, column=0, sticky="ew", pady=(0, 8))

        self.side_label = ttk.Label(parent, text=self.tr("side"))
        self.side_label.grid(row=10, column=0, sticky="w")
        self.side_combo = ttk.Combobox(parent, textvariable=self.side_var, values=["front"], state="readonly", width=34)
        self.side_combo.grid(row=11, column=0, sticky="ew", pady=(2, 8))
        self.side_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_generation_option_changed())

        numeric = ttk.Frame(parent)
        numeric.grid(row=12, column=0, sticky="ew", pady=(2, 8))
        for col in range(4):
            numeric.columnconfigure(col, weight=1)
        self.spinbox_labels = {}
        self.add_spinbox(numeric, "count", self.count_var, 1, 10000, 0)
        self.add_spinbox(numeric, "defect_count_max", self.defect_count_max_var, 1, 10, 1)
        self.add_spinbox(numeric, "samples", self.samples_var, 1, 512, 2)
        self.add_spinbox(numeric, "seed", self.seed_var, 0, 9999999, 3)

        self.output_label = ttk.Label(parent, text=self.tr("output"))
        self.output_label.grid(row=13, column=0, sticky="w")
        out_row = ttk.Frame(parent)
        out_row.grid(row=14, column=0, sticky="ew", pady=(2, 8))
        out_row.columnconfigure(0, weight=1)
        self.output_entry = ttk.Entry(out_row, textvariable=self.output_var, width=36)
        self.output_entry.grid(row=0, column=0, sticky="ew")
        self.output_entry.bind("<KeyRelease>", self.mark_output_manual)
        self.output_browse_button = ttk.Button(out_row, text=self.tr("browse"), command=self.browse_output)
        self.output_browse_button.grid(row=0, column=1, padx=(6, 0))

        self.dry_run_check = ttk.Checkbutton(parent, text=self.tr("dry_run"), variable=self.dry_run_var, command=self.on_generation_option_changed)
        self.dry_run_check.grid(row=15, column=0, sticky="w")
        self.dry_run_help = ttk.Label(parent, text=self.tr("dry_run_help"), wraplength=360, foreground="#555555")
        self.dry_run_help.grid(row=16, column=0, sticky="w", pady=(0, 6))
        self.large_check = ttk.Checkbutton(parent, text=self.tr("large"), variable=self.allow_large_var)
        self.large_check.grid(row=17, column=0, sticky="w")

        buttons = ttk.Frame(parent)
        buttons.grid(row=18, column=0, sticky="ew", pady=(14, 0))
        self.refresh_button = ttk.Button(buttons, text=self.tr("refresh"), command=self.refresh_command_preview)
        self.refresh_button.grid(row=0, column=0, padx=(0, 5), pady=3)
        self.run_button = ttk.Button(buttons, text=self.tr("run"), command=self.run_command)
        self.run_button.grid(row=0, column=1, padx=5, pady=3)
        self.stop_button = ttk.Button(buttons, text=self.tr("stop"), command=self.stop_process)
        self.stop_button.grid(row=0, column=2, padx=5, pady=3)

        self.target_info = tk.Text(parent, width=42, height=11, wrap="word")
        self.target_info.grid(row=19, column=0, sticky="ew", pady=(12, 0))
        self.target_info.configure(state="disabled")

    def add_spinbox(self, parent, label, variable, start, end, column):
        box = ttk.Frame(parent)
        box.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0))
        label_widget = ttk.Label(box, text=self.tr(label))
        label_widget.pack(anchor="w")
        self.spinbox_labels[label] = label_widget
        spin = ttk.Spinbox(box, from_=start, to=end, textvariable=variable, width=8, command=self.refresh_command_preview)
        spin.pack(fill="x")
        spin.bind("<KeyRelease>", lambda _event: self.refresh_command_preview())
        spin.bind("<<Increment>>", lambda _event: self.refresh_command_preview())
        spin.bind("<<Decrement>>", lambda _event: self.refresh_command_preview())

    def build_center_panel(self, parent):
        self.command_preview_label = ttk.Label(parent, text=self.tr("command_preview"))
        self.command_preview_label.grid(row=0, column=0, sticky="w")
        self.command_text = tk.Text(parent, height=5, wrap="word")
        self.command_text.grid(row=1, column=0, sticky="ew", pady=(2, 8))
        self.command_text.configure(state="disabled")

        action_row = ttk.Frame(parent)
        action_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.copy_button = ttk.Button(action_row, text=self.tr("copy"), command=self.copy_command)
        self.copy_button.pack(side="left")
        self.load_button = ttk.Button(action_row, text=self.tr("load"), command=self.load_results)
        self.load_button.pack(side="left", padx=8)
        self.open_button = ttk.Button(action_row, text=self.tr("open"), command=self.open_output)
        self.open_button.pack(side="left")
        ttk.Label(action_row, textvariable=self.status_var).pack(side="right")

        self.log_text = tk.Text(parent, height=25, wrap="word")
        self.log_text.grid(row=3, column=0, sticky="nsew")
        self.log_text.configure(state="disabled")

    def build_right_panel(self, parent):
        preview_top = ttk.Frame(parent)
        preview_top.pack(fill="x")
        self.view_label = ttk.Label(preview_top, text=self.tr("view"))
        self.view_label.pack(side="left")
        self.preview_combo = ttk.Combobox(
            preview_top,
            textvariable=self.preview_mode_var,
            values=["rgb", "masks"],
            state="readonly",
            width=10,
        )
        self.preview_combo.pack(side="left", padx=6)
        self.preview_combo.bind("<<ComboboxSelected>>", lambda _event: self.load_results())
        self.prev_button = ttk.Button(preview_top, text=self.tr("prev"), command=lambda: self.shift_preview(-1))
        self.prev_button.pack(side="left", padx=(12, 3))
        self.next_button = ttk.Button(preview_top, text=self.tr("next"), command=lambda: self.shift_preview(1))
        self.next_button.pack(side="left", padx=3)

        self.preview_label = ttk.Label(parent, text=self.tr("no_image"), anchor="center")
        self.preview_label.pack(fill="both", expand=True, pady=(10, 8))
        self.preview_label.configure(width=46)

        self.summary_text = tk.Text(parent, width=44, height=12, wrap="word")
        self.summary_text.pack(fill="x")
        self.summary_text.configure(state="disabled")

    def browse_python(self):
        path = filedialog.askopenfilename(title="Select Python executable", filetypes=[("Python", "python.exe"), ("All files", "*.*")])
        if path:
            self.python_var.set(path)
            self.refresh_command_preview()

    def browse_output(self):
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.output_is_auto = False
            self.output_var.set(path)
            self.refresh_command_preview()

    def mark_output_manual(self, _event=None):
        if self.output_var.get() != getattr(self, "last_auto_output", ""):
            self.output_is_auto = False
        self.refresh_command_preview()

    def make_default_output_dir(self):
        date_folder = time.strftime("ui_runs_%Y%m%d")
        run_type = "dry_run" if self.dry_run_var.get() else "render"
        target = self.safe_path_part(self.target_var.get() or "target")
        mode = self.safe_path_part(self.mode_var.get() or "mode")
        side = self.safe_path_part(self.side_var.get() or "side")
        run_folder = f"{self.output_run_stamp}_{target}_{mode}_{side}"
        return REPO_ROOT / "defect_dataset_generator" / "outputs" / "dataset" / date_folder / run_type / run_folder

    def current_run_stamp(self):
        return datetime.now().strftime("%H%M%S_%f")[:-3]

    def safe_path_part(self, value):
        allowed = []
        for char in str(value):
            allowed.append(char if char.isalnum() or char in ("-", "_") else "_")
        return "".join(allowed).strip("_") or "item"

    def update_auto_output_path(self, new_stamp=False):
        if not self.output_is_auto:
            return
        if new_stamp:
            self.output_run_stamp = self.current_run_stamp()
        path = self.make_default_output_dir()
        self.last_auto_output = str(path)
        self.output_var.set(str(path))

    def on_generation_option_changed(self):
        self.update_auto_output_path()
        self.refresh_command_preview()

    def on_defect_selection_changed(self):
        self.update_auto_output_path()
        self.refresh_parameter_panel()

    def approved_cooccurrence_labels(self, target):
        return ["+".join(combo) for combo in APPROVED_COOCCURRENCE.get(target, [])]

    def apply_language(self):
        self.master.title(self.tr("title"))
        self.text_widgets["run_setup_frame"].configure(text=self.tr("run_setup"))
        self.text_widgets["command_log_frame"].configure(text=self.tr("command_log"))
        self.text_widgets["result_preview_frame"].configure(text=self.tr("result_preview"))

        self.python_label.configure(text=self.tr("python"))
        self.python_browse_button.configure(text=self.tr("browse"))
        self.language_label.configure(text=self.tr("language"))
        self.target_label.configure(text=self.tr("target"))
        self.mode_label.configure(text=self.tr("mode"))
        for key, button in self.mode_buttons.items():
            button.configure(text=self.tr(key))
        self.defects_label.configure(text=self.tr("defects"))
        self.params_frame.configure(text=self.tr("defect_params"))
        self.side_label.configure(text=self.tr("side"))
        for key, label in self.spinbox_labels.items():
            label.configure(text=self.tr(key))
        self.output_label.configure(text=self.tr("output"))
        self.output_browse_button.configure(text=self.tr("browse"))
        self.dry_run_check.configure(text=self.tr("dry_run"))
        self.dry_run_help.configure(text=self.tr("dry_run_help"))
        self.large_check.configure(text=self.tr("large"))
        self.refresh_button.configure(text=self.tr("refresh"))
        self.run_button.configure(text=self.tr("run"))
        self.stop_button.configure(text=self.tr("stop"))

        self.command_preview_label.configure(text=self.tr("command_preview"))
        self.copy_button.configure(text=self.tr("copy"))
        self.load_button.configure(text=self.tr("load"))
        self.open_button.configure(text=self.tr("open"))
        self.view_label.configure(text=self.tr("view"))
        self.prev_button.configure(text=self.tr("prev"))
        self.next_button.configure(text=self.tr("next"))
        if not self.preview_files:
            self.preview_label.configure(text=self.tr("no_image"))
        self.status_var.set(self.tr("ready"))
        self.refresh_target_details()

    def refresh_target_details(self):
        target = self.target_var.get()
        profile = self.profiles.get(target, {})
        defects = profile.get("supported_defects", [])
        sides = profile.get("default_anchor_sides", ["front"])
        self.side_combo.configure(values=sides)
        if self.side_var.get() not in sides:
            self.side_var.set(sides[0] if sides else "front")

        for child in self.defects_frame.winfo_children():
            child.destroy()
        self.defect_vars = {}
        mode = self.mode_var.get()
        if mode == "cooccurrence":
            self.selected_defect_var.set("")
            combos = self.approved_cooccurrence_labels(target)
            ttk.Label(self.defects_frame, text=self.tr("co_combo")).pack(anchor="w")
            state = "readonly" if combos else "disabled"
            self.cooccurrence_combo = ttk.Combobox(
                self.defects_frame,
                textvariable=self.cooccurrence_var,
                values=combos,
                state=state,
                width=34,
            )
            self.cooccurrence_combo.pack(anchor="w", fill="x", pady=(2, 4))
            self.cooccurrence_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_defect_selection_changed())
            if combos:
                if self.cooccurrence_var.get() not in combos:
                    self.cooccurrence_var.set(combos[0])
            else:
                self.cooccurrence_var.set("")
                ttk.Label(self.defects_frame, text=self.tr("no_combo"), foreground="#777777", wraplength=340).pack(anchor="w")
        elif mode == "single":
            self.cooccurrence_var.set("")
            if defects and self.selected_defect_var.get() not in defects:
                self.selected_defect_var.set(defects[0])
            elif not defects:
                self.selected_defect_var.set("")
            for defect in defects:
                ttk.Radiobutton(
                    self.defects_frame,
                    text=defect,
                    value=defect,
                    variable=self.selected_defect_var,
                    command=self.on_defect_selection_changed,
                ).pack(anchor="w")
        else:
            self.cooccurrence_var.set("")
            self.selected_defect_var.set("")
            ttk.Label(self.defects_frame, text="-", foreground="#777777").pack(anchor="w")

        lines = [
            f"target: {target}",
            f"model: {profile.get('model_id', '')}",
            f"color: {profile.get('appearance_color', '')}",
            f"defects: {', '.join(defects)}",
            f"sides: {', '.join(sides)}",
            f"policy: {profile.get('placement_policy', '')}",
            f"blend: {profile.get('blend_path', '')}",
        ]
        material = profile.get("material_source", {})
        if material:
            lines.append(f"material: {material}")
        target_info = self.targets.get(target, {})
        if target_info.get("current_backend_status"):
            lines.append("")
            lines.append(f"status: {target_info.get('current_backend_status')}")
        self.write_text(self.target_info, "\n".join(lines))
        self.refresh_parameter_panel(refresh=False)
        self.update_auto_output_path()
        self.refresh_command_preview()

    def selected_defects(self):
        if self.mode_var.get() == "cooccurrence":
            value = self.cooccurrence_var.get()
            return value.split("+") if value else []
        if self.mode_var.get() == "single":
            value = self.selected_defect_var.get()
            return [value] if value else []
        return []

    def refresh_parameter_panel(self, refresh=True):
        if not hasattr(self, "params_frame"):
            return
        for child in self.params_frame.winfo_children():
            child.destroy()
        self.param_vars = {}
        self.current_param_specs = {}
        mode = self.mode_var.get()
        defects = self.selected_defects()
        if mode == "normal":
            self.use_custom_params_var.set(False)
            ttk.Label(self.params_frame, text=self.tr("normal_params"), foreground="#777777", wraplength=340).pack(anchor="w")
            if refresh:
                self.refresh_command_preview()
            return
        ttk.Checkbutton(
            self.params_frame,
            text=self.tr("use_custom_params"),
            variable=self.use_custom_params_var,
            command=self.refresh_command_preview,
        ).pack(anchor="w")
        ttk.Button(self.params_frame, text=self.tr("reset_params"), command=self.reset_parameter_defaults).pack(anchor="w", pady=(4, 6))
        if not defects:
            ttk.Label(self.params_frame, text=self.tr("no_params"), foreground="#777777", wraplength=340).pack(anchor="w")
            return
        target = self.target_var.get()
        editable_count = 0
        for defect in defects:
            specs = self.parameter_specs_for(target, defect)
            self.current_param_specs[defect] = specs
            ttk.Label(self.params_frame, text=defect).pack(anchor="w", pady=(4, 1))
            if not specs:
                ttk.Label(self.params_frame, text=self.tr("no_params"), foreground="#777777", wraplength=340).pack(anchor="w")
                continue
            editable_count += len(specs)
            for spec in specs:
                row = ttk.Frame(self.params_frame)
                row.pack(fill="x", pady=1)
                ttk.Label(row, text=spec["label"], width=24).pack(side="left")
                var = tk.StringVar(value=self.format_float(spec["default"]))
                self.param_vars[(defect, spec["key"])] = var
                entry = ttk.Entry(row, textvariable=var, width=10)
                entry.pack(side="left")
                entry.bind("<KeyRelease>", lambda _event: self.refresh_command_preview())
                ttk.Label(row, text=f"{spec['min']}..{spec['max']}", foreground="#777777").pack(side="left", padx=(6, 0))
        if editable_count == 0:
            self.use_custom_params_var.set(False)
        if refresh:
            self.refresh_command_preview()

    def reset_parameter_defaults(self):
        for defect, specs in self.current_param_specs.items():
            for spec in specs:
                var = self.param_vars.get((defect, spec["key"]))
                if var is not None:
                    var.set(self.format_float(spec["default"]))
        self.refresh_command_preview()

    def parameter_specs_for(self, target, defect):
        if defect == "black_dot" and target in self.blackdot_reference_targets():
            return self.blackdot_parameter_specs(target)
        if target == "qc71336_white" and defect == "foreign_material":
            return [
                self.param_spec("defect_count_max", "max count", 1, 1, 10),
                self.param_spec("foreign_material_radius_scale", "radius scale", 0.0, 0.0, 0.05),
                self.param_spec("foreign_material_depth_scale", "depth scale", 0.0, 0.0, 0.2),
            ]
        if target == "qc71336_black" and defect in {"foreign_material", "splay"}:
            return [self.param_spec("defect_count_max", "max count", 1, 1, 10)]
        if target == "qc7_5244_white" and defect == "mixed_color_contamination":
            return [self.param_spec("defect_count_max", "max count", 1, 1, 10)]
        return self.generic_parameter_specs(defect)

    def blackdot_reference_targets(self):
        return {"p101040_blue", "qc71336_white", "qc71336_gray", "qc7_5244_white"}

    def blackdot_parameter_specs(self, target):
        preset_map = (
            self.generation_defaults.get("black_dot_specialized_presets", {})
            .get("default_by_target", {})
        )
        preset_name = preset_map.get(target)
        params = (
            self.black_dot_presets.get("presets", {})
            .get(preset_name, {})
            .get("backend_parameters", {})
        )
        return [
            self.param_spec("black_dot_max_count", "max count", 1, 1, 10),
            self.param_spec("black_dot_radius_min_scale", "radius min scale", params.get("black_dot_radius_min_scale", 0.001), 0.0001, 0.05),
            self.param_spec("black_dot_radius_max_scale", "radius max scale", params.get("black_dot_radius_max_scale", 0.003), 0.0001, 0.05),
            self.param_spec("black_dot_depth_min_scale", "depth min scale", params.get("black_dot_depth_min_scale", 0.002), 0.0001, 0.2),
            self.param_spec("black_dot_depth_max_scale", "depth max scale", params.get("black_dot_depth_max_scale", 0.006), 0.0001, 0.2),
        ]

    def generic_parameter_specs(self, defect):
        defaults = self.generation_defaults.get("defect_defaults", {}).get(defect, {})
        size_range = defaults.get("size_factor_range", [0.012, 0.035])
        specs = [
            self.param_spec("defect_count_max", "max count", 1, 1, 10),
            self.param_spec("size_factor_min", "size factor min", size_range[0], 0.0001, 0.2),
            self.param_spec("size_factor_max", "size factor max", size_range[1], 0.0001, 0.2),
            self.param_spec("size_scale", "size scale", defaults.get("size_scale", 1.0), 0.1, 5.0),
        ]
        if "width_multiplier" in defaults:
            specs.append(self.param_spec("width_multiplier", "width multiplier", defaults["width_multiplier"], 0.05, 20.0))
        if "height_multiplier" in defaults:
            specs.append(self.param_spec("height_multiplier", "height multiplier", defaults["height_multiplier"], 0.05, 20.0))
        material = defaults.get("material", {})
        if "roughness" in material:
            specs.append(self.param_spec("roughness", "roughness", material["roughness"], 0.0, 1.0))
        return specs

    def param_spec(self, key, label, default, min_value, max_value):
        return {"key": key, "label": label, "default": float(default), "min": float(min_value), "max": float(max_value)}

    def format_float(self, value):
        return ("{0:.6f}".format(float(value))).rstrip("0").rstrip(".")

    def collect_defect_params(self):
        if self.mode_var.get() == "normal" or not self.use_custom_params_var.get():
            return {}
        defects_payload = {}
        for defect, specs in self.current_param_specs.items():
            values = {}
            for spec in specs:
                var = self.param_vars.get((defect, spec["key"]))
                if var is None:
                    continue
                text = var.get().strip()
                if not text:
                    raise ValueError(f"{defect}.{spec['key']} cannot be empty.")
                try:
                    number = float(text)
                except ValueError:
                    raise ValueError(f"{defect}.{spec['key']} must be a number.") from None
                if number < spec["min"] or number > spec["max"]:
                    raise ValueError(f"{defect}.{spec['key']} must be between {spec['min']} and {spec['max']}.")
                values[spec["key"]] = number
            if values:
                self.validate_parameter_pairs(defect, values)
                defects_payload[defect] = values
        if not defects_payload:
            return {}
        return {
            "schema_version": "ui_defect_params_v1",
            "target": self.target_var.get(),
            "mode": self.mode_var.get(),
            "defects": defects_payload,
        }

    def validate_parameter_pairs(self, defect, values):
        pairs = [
            ("size_factor_min", "size_factor_max"),
            ("black_dot_radius_min_scale", "black_dot_radius_max_scale"),
            ("black_dot_depth_min_scale", "black_dot_depth_max_scale"),
        ]
        for min_key, max_key in pairs:
            if min_key in values and max_key in values and values[min_key] > values[max_key]:
                raise ValueError(f"{defect}.{min_key} cannot be greater than {defect}.{max_key}.")

    def defect_params_file_path(self):
        return Path(self.output_var.get()) / "ui_defect_params.json"

    def write_defect_params_file(self):
        payload = self.collect_defect_params()
        if not payload:
            return None
        path = self.defect_params_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def build_command(self):
        mode = self.mode_var.get()
        target = self.target_var.get()
        defects = self.selected_defects()
        output = Path(self.output_var.get())
        side = self.side_var.get()
        command = [self.python_var.get(), str(APP_PATH)]

        if mode == "normal":
            command += ["generate-target-normal", "--target", target]
        elif mode == "cooccurrence":
            command += ["generate-target-cooccurrence", "--target", target, "--defects", ",".join(defects)]
        else:
            command += ["generate-target", "--target", target, "--defects", ",".join(defects[:1])]

        command += [
            "--count",
            str(self.count_var.get()),
            "--out",
            str(output),
            "--samples",
            str(self.samples_var.get()),
            "--seed",
            str(self.seed_var.get()),
            "--anchor-sides",
            side,
        ]
        if mode == "single":
            command += ["--defect-count-max", str(int(self.defect_count_max_var.get()))]
        if self.dry_run_var.get():
            command.append("--dry-run")
        params_payload = self.collect_defect_params()
        if params_payload:
            command.extend(["--defect-params-json", str(self.defect_params_file_path())])
        return command

    def validate_command(self):
        mode = self.mode_var.get()
        defects = self.selected_defects()
        if mode == "single" and len(defects) != 1:
            raise ValueError("Single mode requires exactly one selected defect.")
        if mode == "cooccurrence":
            approved = APPROVED_COOCCURRENCE.get(self.target_var.get(), [])
            if tuple(defects) not in approved:
                raise ValueError("Cooccurrence mode only supports the approved combo listed in the dropdown.")
        if self.count_var.get() > 20 and not self.allow_large_var.get():
            raise ValueError("Count is greater than 20. Enable the large-count checkbox first.")
        if not Path(self.python_var.get()).exists():
            raise ValueError("Python executable does not exist.")
        if not APP_PATH.exists():
            raise ValueError("app.py was not found.")
        self.collect_defect_params()

    def refresh_command_preview(self):
        try:
            command = self.build_command()
            text = subprocess.list2cmdline(command)
        except Exception as exc:
            text = f"Cannot build command: {exc}"
        self.command_var.set(text)
        self.write_text(self.command_text, text)

    def run_command(self):
        if self.process is not None and self.process.poll() is None:
            messagebox.showwarning("Run in progress", "A UI-started process is already running.")
            return
        self.update_auto_output_path(new_stamp=True)
        try:
            self.validate_command()
        except Exception as exc:
            messagebox.showerror("Invalid command", str(exc))
            return
        output = Path(self.output_var.get())
        if output.exists() and any(output.iterdir()) and not self.dry_run_var.get():
            ok = messagebox.askyesno("Output exists", "The output folder is not empty. Continue?")
            if not ok:
                return
        output.mkdir(parents=True, exist_ok=True)
        try:
            self.write_defect_params_file()
        except Exception as exc:
            messagebox.showerror("Invalid parameters", str(exc))
            return
        command = self.build_command()
        self.refresh_command_preview()
        self.status_var.set("Running")
        self.append_log(f"$ {subprocess.list2cmdline(command)}")
        worker = threading.Thread(target=self.run_process_worker, args=(command,), daemon=True)
        worker.start()

    def run_process_worker(self, command):
        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(REPO_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
            )
            for line in self.process.stdout:
                self.log_queue.put(("log", line.rstrip()))
            return_code = self.process.wait()
            self.log_queue.put(("done", return_code))
        except Exception as exc:
            self.log_queue.put(("error", str(exc)))

    def stop_process(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            self.append_log("Stop requested for UI-started process.")
            self.status_var.set("Stopping")

    def poll_log_queue(self):
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self.append_log(payload)
                elif kind == "done":
                    self.status_var.set(f"Finished: {payload}")
                    self.append_log(f"Process finished with exit code {payload}.")
                    self.load_results()
                    self.process = None
                elif kind == "error":
                    self.status_var.set("Error")
                    self.append_log(f"ERROR: {payload}")
                    self.process = None
        except queue.Empty:
            pass
        self.master.after(200, self.poll_log_queue)

    def load_results(self):
        root = Path(self.output_var.get())
        mode = self.preview_mode_var.get()
        if mode not in ("rgb", "masks"):
            mode = "rgb"
            self.preview_mode_var.set(mode)
        search_dirs = [root / mode]
        if mode == "masks":
            search_dirs.append(root / "mask")
        files = []
        for folder in search_dirs:
            if folder.exists():
                files.extend(sorted(folder.glob("*.png")))
                files.extend(sorted(folder.glob("*.jpg")))
        self.preview_files = files
        self.preview_index = min(self.preview_index, max(0, len(files) - 1))
        self.show_preview()
        self.update_summary(root)

    def show_preview(self):
        if not self.preview_files:
            root = Path(self.output_var.get())
            label = self.tr("dry_run_no_image") if self.is_dry_run_output(root) else self.tr("no_image")
            self.preview_label.configure(text=label, image="")
            self.preview_image = None
            return
        path = self.preview_files[self.preview_index]
        if Image is None or ImageTk is None:
            self.preview_label.configure(text=str(path), image="")
            return
        image = Image.open(path).convert("RGB")
        image.thumbnail((430, 430), Image.LANCZOS)
        self.preview_image = ImageTk.PhotoImage(image)
        self.preview_label.configure(image=self.preview_image, text="")
        self.status_var.set(f"{self.preview_index + 1}/{len(self.preview_files)} {path.name}")

    def shift_preview(self, delta):
        if not self.preview_files:
            return
        self.preview_index = (self.preview_index + delta) % len(self.preview_files)
        self.show_preview()

    def update_summary(self, root):
        rgb_count = len(list((root / "rgb").glob("*.png"))) if (root / "rgb").exists() else 0
        mask_folder = root / "masks" if (root / "masks").exists() else root / "mask"
        mask_count = len(list(mask_folder.glob("*.png"))) if mask_folder.exists() else 0
        label_count = len(list((root / "labels_yolo").glob("*.txt"))) if (root / "labels_yolo").exists() else 0
        empty_masks = self.count_empty_masks(mask_folder) if mask_folder.exists() else None
        dry_run = self.is_dry_run_output(root)
        lines = [
            f"output: {root}",
            f"dry_run: {dry_run}",
            f"rgb: {rgb_count}",
            f"masks: {mask_count}",
            f"labels: {label_count}",
            f"empty masks: {empty_masks if empty_masks is not None else 'n/a'}",
            f"generation_plan.json: {(root / 'generation_plan.json').exists()}",
            f"backend_run_log.json: {(root / 'backend_run_log.json').exists()}",
        ]
        if dry_run:
            lines.append("")
            lines.append(self.tr("dry_run_no_image"))
        self.write_text(self.summary_text, "\n".join(lines))

    def is_dry_run_output(self, root):
        for name in ("backend_run_log.json", "target_generation_summary.json", "generation_plan.json"):
            path = root / name
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("dry_run") is True or data.get("status") == "planned":
                return True
        return False

    def count_empty_masks(self, folder):
        if Image is None:
            return "Pillow unavailable"
        count = 0
        for path in folder.glob("*.png"):
            image = Image.open(path).convert("L")
            if image.getbbox() is None:
                count += 1
        return count

    def copy_command(self):
        self.master.clipboard_clear()
        self.master.clipboard_append(self.command_var.get())
        self.status_var.set("Command copied")

    def open_output(self):
        path = Path(self.output_var.get())
        path.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(path))
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def append_log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def write_text(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.configure(state="disabled")


def main():
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    app = DefectGenerationUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
