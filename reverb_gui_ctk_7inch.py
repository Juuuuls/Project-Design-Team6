# reverb_gui_ctk_7inch.py
# Project Design T6 - Build 1.0 7
# Optimized for Waveshare 7" (1024x600). Sleek black + hot pink. Frequency field removed.
# Features:
#  - Start/Stop live capture (calls datagatherer_po2_g.py)
#  - Deploy Class to Sheet (classifies rt60 => Dead/Neutral/Hot and updates Google Sheet)
#  - Compact layout for 1024x600

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

# Path to backend script (same folder)
SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datagatherer_po2_g.py")

# Angle constants
MAX_ANGLE = 355
ANGLE_STEP = 5
MAX_ROWS = MAX_ANGLE // ANGLE_STEP + 1  # 72

# Theme
PINK = "#ff4dc4"
PINK_HOVER = "#ff73d9"
DARK = "#0b0b0e"
DARK2 = "#141419"
TEXT_DIM = "#cfcfe0"


def classify_rt60(rt60: float) -> str:
    """Rule-based classifier using RT60 only."""
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

        # Window setup for 7" 1024x600
        ctk.set_appearance_mode("dark")
        self.title("Project Design T6 - Build 1.0 7")
        self.geometry("1024x600")
        self.minsize(1000, 580)
        self.configure(fg_color=DARK)

        # Fullscreen toggles (optional)
        self.bind("<F11>", lambda e: self.attributes("-fullscreen", True))
        self.bind("<Escape>", lambda e: self.attributes("-fullscreen", False))

        # Runtime
        self.proc = None
        self.proc_thread = None
        self.stop_requested = False

        self._build_ui()

    # ----------------- UI -----------------
    def _build_ui(self):
        # HEADER (compact for small height)
        top = ctk.CTkFrame(self, fg_color=DARK2, corner_radius=12)
        top.pack(fill="x", padx=10, pady=(10, 6))

        title = ctk.CTkLabel(
            top, text="🎧 Project Design T6 - Build 1.0 7",
            font=("Segoe UI Semibold", 18), text_color=PINK
        )
        title.pack(side="left", padx=10, pady=6)

        subtitle = ctk.CTkLabel(
            top, text="Angle Capture • 0–355° • 1°/s or 5°/s",
            font=("Segoe UI", 12), text_color=TEXT_DIM
        )
        subtitle.pack(side="left", padx=8)

        # BODY (two rows: controls + log)
        body = ctk.CTkFrame(self, fg_color=DARK2, corner_radius=12)
        body.pack(fill="x", padx=10, pady=(0, 6))

        # Row 1: Port + Rows + Speed + Toggles
        row1 = ctk.CTkFrame(body, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(8, 4))

        # Port
        ctk.CTkLabel(row1, text="Port", text_color=TEXT_DIM, font=("Segoe UI", 12)).pack(side="left", padx=(0, 6))
        default_port = "COM5" if platform.system() == "Windows" else "/dev/ttyUSB0"
        self.port_var = ctk.StringVar(value=default_port)
        self.port_combo = ctk.CTkComboBox(
            row1,
            values=self._scan_ports(),
            variable=self.port_var,
            width=220,
            fg_color="#181820",
            border_color=PINK,
            button_color=PINK,
            text_color="white",
            corner_radius=8
        )
        self.port_combo.pack(side="left")
        ctk.CTkButton(
            row1, text="↻", width=36, command=self._refresh_ports,
            fg_color=PINK, hover_color=PINK_HOVER, corner_radius=8
        ).pack(side="left", padx=6)

        # Rows
        ctk.CTkLabel(row1, text=f"Rows (≤ {MAX_ROWS})", text_color=TEXT_DIM, font=("Segoe UI", 12)).pack(side="left", padx=(12, 6))
        self.count_var = ctk.IntVar(value=MAX_ROWS)
        ctk.CTkEntry(row1, width=80, textvariable=self.count_var,
                     fg_color="#181820", border_color=PINK, corner_radius=8).pack(side="left")

        # Speed
        ctk.CTkLabel(row1, text="Angle Speed (°/s)", text_color=TEXT_DIM, font=("Segoe UI", 12)).pack(side="left", padx=(12, 6))
        self.speed_var = ctk.StringVar(value="5")
        self.speed_segment = ctk.CTkSegmentedButton(
            row1, values=["1", "5"], variable=self.speed_var,
            fg_color="#181820",
            selected_color=PINK, selected_hover_color=PINK_HOVER,
            unselected_color="#23232b", unselected_hover_color="#2c2c36",
            text_color=("white", "white"),
            corner_radius=8
        )
        self.speed_segment.pack(side="left")

        # Toggles
        row1b = ctk.CTkFrame(body, fg_color="transparent")
        row1b.pack(fill="x", padx=10, pady=(0, 8))

        self.sim_var = ctk.BooleanVar(value=False)
        self.skip_var = ctk.BooleanVar(value=False)

        ctk.CTkCheckBox(row1b, text="Simulate (no serial)",
                        variable=self.sim_var, fg_color=PINK, border_color=PINK,
                        corner_radius=8, font=("Segoe UI", 12)).pack(side="left", padx=(0, 12))
        ctk.CTkCheckBox(row1b, text="Skip Google Sheets upload",
                        variable=self.skip_var, fg_color=PINK, border_color=PINK,
                        corner_radius=8, font=("Segoe UI", 12)).pack(side="left")

        # Advanced Panel (compact)
        adv = ctk.CTkFrame(body, fg_color="#121217", corner_radius=10)
        adv.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkLabel(adv, text="Advanced", text_color=PINK, font=("Segoe UI Semibold", 13)).grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 6)
        )

        # Sheet link
        ctk.CTkLabel(adv, text="Sheet Link", text_color=TEXT_DIM, font=("Segoe UI", 12)).grid(row=1, column=0, sticky="w", padx=10, pady=4)
        self.sheet_var = ctk.StringVar(
            value="https://docs.google.com/spreadsheets/d/12YI-C_c9Hmq-uzDdm9qrlsCrjmMmt7b4P0kJVjFM-98/edit?usp=sharing"
        )
        ctk.CTkEntry(adv, textvariable=self.sheet_var, width=640,
                     fg_color="#181820", border_color=PINK, corner_radius=8).grid(row=1, column=1, sticky="we", padx=8, pady=4)

        # Service JSON
        ctk.CTkLabel(adv, text="Service JSON", text_color=TEXT_DIM, font=("Segoe UI", 12)).grid(row=2, column=0, sticky="w", padx=10, pady=4)
        default_json = os.path.join(os.path.dirname(SCRIPT_PATH), "projectdesignt6-b8c2872f2067.json")
        self.json_var = ctk.StringVar(value=default_json)
        ctk.CTkEntry(adv, textvariable=self.json_var, width=640,
                     fg_color="#181820", border_color=PINK, corner_radius=8).grid(row=2, column=1, sticky="we", padx=8, pady=4)

        # Model Path (optional; kept for backend compatibility)
        ctk.CTkLabel(adv, text="Model Path (.joblib)", text_color=TEXT_DIM, font=("Segoe UI", 12)).grid(row=3, column=0, sticky="w", padx=10, pady=4)
        self.model_var = ctk.StringVar(value=os.path.join(os.path.dirname(SCRIPT_PATH), "reverb_zone_rf.joblib"))
        ctk.CTkEntry(adv, textvariable=self.model_var, width=640,
                     fg_color="#181820", border_color=PINK, corner_radius=8).grid(row=3, column=1, sticky="we", padx=8, pady=4)

        # Info note (replaces old frequency inputs)
        ctk.CTkLabel(
            adv,
            text="Classifier: RT60-only (Dead < 0.2 s • Neutral 0.2–0.4 s • Hot > 0.4 s)",
            text_color=TEXT_DIM, font=("Segoe UI", 11)
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 10))

        adv.grid_columnconfigure(1, weight=1)

        # Controls (Start/Stop/Deploy)
        controls = ctk.CTkFrame(self, fg_color=DARK2, corner_radius=12)
        controls.pack(fill="x", padx=10, pady=(0, 6))

        self.start_btn = ctk.CTkButton(
            controls, text="▶ Start Capture", command=self.start,
            fg_color=PINK, hover_color=PINK_HOVER, corner_radius=10, width=140
        )
        self.start_btn.pack(side="left", padx=8, pady=8)

        self.stop_btn = ctk.CTkButton(
            controls, text="■ Stop", command=self.stop,
            fg_color="#282838", hover_color="#34344a", corner_radius=10, width=70
        )
        self.stop_btn.pack(side="left", padx=6, pady=8)

        self.deploy_btn = ctk.CTkButton(
            controls, text="🚀 Deploy Class to Sheet", command=self.deploy_to_gsheet,
            fg_color=PINK, hover_color=PINK_HOVER, corner_radius=10, width=220
        )
        self.deploy_btn.pack(side="left", padx=8, pady=8)

        self.progress = ctk.CTkProgressBar(
            controls, width=300, progress_color=PINK, fg_color="#1b1b23"
        )
        self.progress.set(0)
        self.progress.pack(side="right", padx=10, pady=10)

        # LOG (fills remaining space)
        log_wrap = ctk.CTkFrame(self, fg_color=DARK2, corner_radius=12)
        log_wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.log = ctk.CTkTextbox(
            log_wrap, fg_color="#0f0f15", text_color=PINK,
            corner_radius=10, wrap="word", font=("Consolas", 10)
        )
        self.log.pack(fill="both", expand=True, padx=8, pady=8)
        self._write("💗 Ready — optimized for 1024×600. IDs are angles 0..355 (step 5). Choose 1°/s or 5°/s.")

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
        return ports or (["COM3", "COM5"] if platform.system() == "Windows" else ["/dev/ttyUSB0", "/dev/ttyACM0"])

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
            # keep model path for backend compatibility (ignored by rule-only)
            "--model-path", self.model_var.get().strip(),
        ]

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

                # normalize names from earlier versions
                if "rt60" not in df.columns and "RT60" in df.columns:
                    df.rename(columns={"RT60": "rt60"}, inplace=True)
                if "utv" not in df.columns and "Ultrasonic Value" in df.columns:
                    df.rename(columns={"Ultrasonic Value": "utv"}, inplace=True)
                if "angle" not in df.columns and "number" in df.columns:
                    df.rename(columns={"number": "angle"}, inplace=True)

                # require angle, rt60, utv
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
