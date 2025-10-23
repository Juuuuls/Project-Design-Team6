# reverb_gui_ctk_pink.py
# Sleek black + hot pink GUI for Reverberation Taker system
# Frequency field removed for cleaner UI
# Includes: Deploy Class to Sheet (rule-based RT60 classification)

import os
import sys
import subprocess
import threading
import time
import platform
import re

try:
    import customtkinter as ctk
except ModuleNotFoundError:
    raise SystemExit("❌ Please install CustomTkinter:\n  pip install customtkinter")

# optional for port scan
try:
    import serial.tools.list_ports as list_ports
except Exception:
    list_ports = None

# optional for deploy button
try:
    import pandas as pd
except Exception:
    pd = None

try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception:
    gspread = None
    Credentials = None

SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datagatherer_po2_g.py")

MAX_ANGLE = 355
ANGLE_STEP = 5
MAX_ROWS = MAX_ANGLE // ANGLE_STEP + 1  # 72

# 💖 Theme colors
PINK = "#ff4dc4"
PINK_HOVER = "#ff73d9"
DARK = "#0d0d0f"
DARK2 = "#17171b"
TEXT_DIM = "#d9d9e0"


def classify_rt60(rt60: float) -> str:
    """Your rule-based classifier."""
    try:
        r = float(rt60)
    except Exception:
        return ""
    if r < 0.2:
        return "Dead Spot"
    elif r <= 0.4:
        return "Neutral Zone"
    else:
        return "Hot Spot"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        self.title("Project Design T6 - Build 1.0")
        self.geometry("1000x760")
        self.minsize(980, 700)
        self.configure(fg_color=DARK)

        self.proc = None
        self.proc_thread = None
        self.stop_requested = False

        self._build_ui()

    # ----------------- UI -----------------
    def _build_ui(self):
        # Header
        top = ctk.CTkFrame(self, fg_color=DARK2, corner_radius=14)
        top.pack(fill="x", padx=14, pady=(14, 10))

        title = ctk.CTkLabel(
            top, text="Project Design T6 - Build 1.0",
            font=("Segoe UI Semibold", 22), text_color=PINK
        )
        title.pack(side="left", padx=12, pady=10)

        subtitle = ctk.CTkLabel(
            top, text="Angle-based Capture • 0–355° • 1°/s or 5°/s",
            font=("Segoe UI", 14), text_color=TEXT_DIM
        )
        subtitle.pack(side="left", padx=8)

        # Body
        body = ctk.CTkFrame(self, fg_color=DARK2, corner_radius=14)
        body.pack(fill="x", padx=14, pady=(0, 10))

        # Row 1: Port
        row1 = ctk.CTkFrame(body, fg_color="transparent")
        row1.pack(fill="x", padx=14, pady=(14, 6))

        ctk.CTkLabel(row1, text="Port", text_color=TEXT_DIM).pack(side="left", padx=(0, 8))

        default_port = "COM5" if platform.system() == "Windows" else "/dev/ttyUSB0"
        self.port_var = ctk.StringVar(value=default_port)
        self.port_combo = ctk.CTkComboBox(
            row1,
            values=self._scan_ports(),
            variable=self.port_var,
            width=250,
            fg_color="#1a1a22",
            border_color=PINK,
            button_color=PINK,
            text_color="white"
        )
        self.port_combo.pack(side="left")

        ctk.CTkButton(row1, text="↻ Scan", command=self._refresh_ports,
                      fg_color=PINK, hover_color=PINK_HOVER).pack(side="left", padx=8)

        # Row 2: Rows + Angle Speed
        row2 = ctk.CTkFrame(body, fg_color="transparent")
        row2.pack(fill="x", padx=14, pady=6)

        ctk.CTkLabel(row2, text=f"Rows (≤ {MAX_ROWS})", text_color=TEXT_DIM).pack(side="left", padx=(0, 8))
        self.count_var = ctk.IntVar(value=MAX_ROWS)
        ctk.CTkEntry(row2, width=90, textvariable=self.count_var,
                     fg_color="#1a1a22", border_color=PINK).pack(side="left")

        ctk.CTkLabel(row2, text="Angle Speed (°/s)", text_color=TEXT_DIM).pack(side="left", padx=(16, 8))
        self.speed_var = ctk.StringVar(value="5")
        self.speed_segment = ctk.CTkSegmentedButton(
            row2, values=["1", "5"], variable=self.speed_var,
            fg_color="#1a1a22",
            selected_color=PINK, selected_hover_color=PINK_HOVER,
            unselected_color="#25252d", unselected_hover_color="#2c2c36",
            text_color=("white", "white")
        )
        self.speed_segment.pack(side="left")

        # Row 3: Toggles
        row3 = ctk.CTkFrame(body, fg_color="transparent")
        row3.pack(fill="x", padx=14, pady=6)

        self.sim_var = ctk.BooleanVar(value=False)
        self.skip_var = ctk.BooleanVar(value=False)

        ctk.CTkCheckBox(row3, text="Simulate (no serial)",
                        variable=self.sim_var, fg_color=PINK, border_color=PINK).pack(side="left", padx=(0, 18))
        ctk.CTkCheckBox(row3, text="Skip Google Sheets upload",
                        variable=self.skip_var, fg_color=PINK, border_color=PINK).pack(side="left")

        # Advanced panel
        self.adv_panel = ctk.CTkFrame(self, fg_color="#131317", corner_radius=10)
        self.adv_panel.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkLabel(self.adv_panel, text="Advanced Settings", text_color=PINK).grid(
            row=0, column=0, sticky="w", padx=12, pady=10
        )

        # Sheet link
        ctk.CTkLabel(self.adv_panel, text="Sheet Link", text_color=TEXT_DIM).grid(row=1, column=0, sticky="w", padx=12)
        self.sheet_var = ctk.StringVar(
            value="https://docs.google.com/spreadsheets/d/12YI-C_c9Hmq-uzDdm9qrlsCrjmMmt7b4P0kJVjFM-98/edit?usp=sharing"
        )
        ctk.CTkEntry(self.adv_panel, textvariable=self.sheet_var, width=640,
                     fg_color="#1a1a22", border_color=PINK).grid(row=1, column=1, sticky="we", padx=10, pady=6)

        # Service JSON
        ctk.CTkLabel(self.adv_panel, text="Service JSON", text_color=TEXT_DIM).grid(row=2, column=0, sticky="w", padx=12)
        default_json = os.path.join(os.path.dirname(SCRIPT_PATH), "projectdesignt6-b8c2872f2067.json")
        self.json_var = ctk.StringVar(value=default_json)
        ctk.CTkEntry(self.adv_panel, textvariable=self.json_var, width=640,
                     fg_color="#1a1a22", border_color=PINK).grid(row=2, column=1, sticky="we", padx=10, pady=6)

        # Model Path (kept for compatibility; not used by rule-based deploy)
        ctk.CTkLabel(self.adv_panel, text="Model Path (.joblib)", text_color=TEXT_DIM).grid(row=3, column=0, sticky="w", padx=12)
        self.model_var = ctk.StringVar(value=os.path.join(os.path.dirname(SCRIPT_PATH), "reverb_zone_rf.joblib"))
        ctk.CTkEntry(self.adv_panel, textvariable=self.model_var, width=640,
                     fg_color="#1a1a22", border_color=PINK).grid(row=3, column=1, sticky="we", padx=10, pady=6)

        # Info note to replace removed Frequency field
        ctk.CTkLabel(
            self.adv_panel,
            text="Classifier: Rule-based on RT60 only (Dead < 0.2 s • Neutral 0.2–0.4 s • Hot > 0.4 s)",
            text_color=TEXT_DIM, font=("Segoe UI", 12)
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 12))

        self.adv_panel.grid_columnconfigure(1, weight=1)

        # Controls row: Start/Stop + Deploy
        controls = ctk.CTkFrame(self, fg_color=DARK2, corner_radius=14)
        controls.pack(fill="x", padx=14, pady=(0, 10))

        self.start_btn = ctk.CTkButton(controls, text="▶ Start Capture",
                                       command=self.start, fg_color=PINK, hover_color=PINK_HOVER)
        self.start_btn.pack(side="left", padx=12, pady=12)

        self.stop_btn = ctk.CTkButton(controls, text="■ Stop",
                                      command=self.stop, fg_color="#2a2a34", hover_color="#3a3a48")
        self.stop_btn.pack(side="left", padx=(6, 12), pady=12)

        # NEW: Deploy button
        self.deploy_btn = ctk.CTkButton(controls, text="🚀 Deploy Class to Sheet",
                                        command=self.deploy_to_gsheet,
                                        fg_color=PINK, hover_color=PINK_HOVER)
        self.deploy_btn.pack(side="left", padx=(6, 12), pady=12)

        self.progress = ctk.CTkProgressBar(controls, width=360, progress_color=PINK, fg_color="#1a1a22")
        self.progress.set(0)
        self.progress.pack(side="right", padx=14, pady=14)

        # Log
        log_wrap = ctk.CTkFrame(self, fg_color=DARK2, corner_radius=14)
        log_wrap.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        self.log = ctk.CTkTextbox(
            log_wrap, fg_color="#101015", text_color=PINK,
            corner_radius=12, wrap="word", font=("Consolas", 11)
        )
        self.log.pack(fill="both", expand=True, padx=12, pady=12)
        self._write("💗 Ready — Angles 0..355° (step 5). Choose 1°/s or 5°/s speed.")

    # ----------------- Helpers -----------------
    def _write(self, text: str):
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.update_idletasks()

    def _scan_ports(self):
        ports = []
        if list_ports:
            try:
                for p in list_ports.comports():
                    ports.append(p.device)
            except Exception:
                pass
        return ports or (["COM3", "COM5"] if platform.system() == "Windows" else ["/dev/ttyUSB0"])

    def _refresh_ports(self):
        self.port_combo.configure(values=self._scan_ports())

    # ----------------- Capture start/stop -----------------
    def start(self):
        if self.proc and self.proc.poll() is None:
            self._write("⚠️ Already running.")
            return

        # rows
        try:
            count = int(self.count_var.get() or MAX_ROWS)
        except Exception:
            count = MAX_ROWS
        count = max(1, min(count, MAX_ROWS))

        # speed -> interval
        speed = int(self.speed_var.get())
        interval = ANGLE_STEP / speed

        port = self.port_var.get().strip()
        cmd = [
            sys.executable, SCRIPT_PATH,
            "--port", port,
            "--count", str(count),
            "--max-angle", str(MAX_ANGLE),
            "--angle-step", str(ANGLE_STEP),
            "--angle-speed", str(speed),
            "--interval", f"{interval:.3f}",
            "--sheet-link", self.sheet_var.get().strip(),
            "--service-json", self.json_var.get().strip(),
            # keep model-path for compatibility; backend can ignore it
            "--model-path", self.model_var.get().strip(),
        ]

        # note: checkboxes exist; ensure attributes
        if not hasattr(self, "sim_var"):
            self.sim_var = ctk.BooleanVar(value=False)
        if not hasattr(self, "skip_var"):
            self.skip_var = ctk.BooleanVar(value=False)

        if self.sim_var.get():
            cmd.append("--simulate")
        if self.skip_var.get():
            cmd.append("--skip-gsheets")

        self._write(f"▶ Running: {' '.join(cmd)}")

        self.stop_requested = False
        self.progress.set(0)

        def run():
            try:
                self.proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                )
                start = time.time()
                for line in self.proc.stdout:
                    if self.stop_requested:
                        self.proc.terminate()
                        break
                    self._write(line.strip())
                    self.progress.set((time.time() - start) % 1.0)
                self.proc.wait()
                self._write("✅ Done!" if not self.stop_requested else "⏹ Stopped by user.")
            except FileNotFoundError:
                self._write("❌ datagatherer_po2_g.py not found!")
            except Exception as e:
                self._write(f"❌ Error: {e}")
            finally:
                self.progress.set(0)
                self.proc = None

        self.proc_thread = threading.Thread(target=run, daemon=True)
        self.proc_thread.start()

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.stop_requested = True
            self._write("…Stopping process…")
        else:
            self._write("ℹ️ Nothing is running.")

    # ----------------- Deploy classification to Google Sheet -----------------
    def deploy_to_gsheet(self):
        """Reads Sheet, computes 'class' from 'rt60', writes back."""
        if gspread is None or Credentials is None or pd is None:
            self._write("❌ Missing packages. Install:\n  pip install gspread google-auth pandas")
            return

        sheet_url = self.sheet_var.get().strip()
        json_path = self.json_var.get().strip()
        if not sheet_url:
            self._write("❌ Provide a Google Sheet URL.")
            return
        if not json_path or not os.path.isfile(json_path):
            self._write("❌ Service Account JSON not found at the given path.")
            return

        self._write("🚀 Deploying classification to Google Sheet...")
        self.deploy_btn.configure(state="disabled")
        self.update_idletasks()

        def worker():
            try:
                scopes = [
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive",
                ]
                creds = Credentials.from_service_account_file(json_path, scopes=scopes)
                client = gspread.authorize(creds)

                m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", sheet_url)
                if not m:
                    raise ValueError("Invalid Google Sheet URL")
                sheet_id = m.group(1)

                sh = client.open_by_key(sheet_id)
                ws = sh.sheet1

                self._write("→ Downloading sheet...")
                rows = ws.get_all_records()  # list of dicts
                if not rows:
                    raise ValueError("Sheet is empty.")

                df = pd.DataFrame(rows)

                # normalize rt60 column name
                if "rt60" not in df.columns and "RT60" in df.columns:
                    df.rename(columns={"RT60": "rt60"}, inplace=True)
                if "utv" not in df.columns and "Ultrasonic Value" in df.columns:
                    df.rename(columns={"Ultrasonic Value": "utv"}, inplace=True)
                if "angle" not in df.columns and "number" in df.columns:
                    df.rename(columns={"number": "angle"}, inplace=True)

                # check required columns
                for col in ("angle", "rt60", "utv"):
                    if col not in df.columns:
                        raise ValueError(f"Required column '{col}' not found. Expect: angle | rt60 | utv")

                self._write(f"→ {len(df)} rows loaded. Classifying...")
                df["class"] = df["rt60"].apply(classify_rt60)

                self._write("→ Uploading updated sheet...")
                ws.clear()
                ws.update([df.columns.tolist()] + df.astype(object).values.tolist())

                self._write("✅ Deploy complete. Sheet updated.")
            except Exception as e:
                self._write(f"❌ Deploy error: {e}")
            finally:
                self.deploy_btn.configure(state="normal")

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()