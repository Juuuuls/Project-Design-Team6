# deploy_model_gui.py
# GUI tool to classify RT60 values and update Google Sheet with a "class" column.

import os
import pandas as pd
import customtkinter as ctk
from tkinter import messagebox
import gspread
from google.oauth2.service_account import Credentials

# ------------------- RT60 classification logic -------------------
def classify_rt60(rt60):
    if rt60 < 0.2:
        return "Dead Spot"
    elif rt60 <= 0.4:
        return "Neutral Zone"
    else:
        return "Hot Spot"

# ------------------- GSheet helpers -------------------
def connect_sheet(sheet_url, json_path):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(json_path, scopes=scopes)
    client = gspread.authorize(creds)

    import re
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", sheet_url)
    if not m:
        raise ValueError("Invalid Google Sheet URL")
    sheet_id = m.group(1)

    sh = client.open_by_key(sheet_id)
    ws = sh.sheet1
    return ws

def update_class_column(ws):
    # Download entire sheet into a DataFrame
    data = ws.get_all_records()
    if not data:
        messagebox.showerror("Empty Sheet", "No data found in the Google Sheet.")
        return
    df = pd.DataFrame(data)

    # Expect columns: angle | rt60 | utv
    if "rt60" not in df.columns and "RT60" in df.columns:
        df.rename(columns={"RT60": "rt60"}, inplace=True)

    if "rt60" not in df.columns:
        messagebox.showerror("Missing Column", "RT60 column not found in sheet.")
        return

    # Classify
    df["class"] = df["rt60"].apply(classify_rt60)

    # Upload back (replace all)
    ws.clear()
    ws.update([df.columns.values.tolist()] + df.values.tolist())
    messagebox.showinfo("Success", f"✅ Updated {len(df)} rows with classification results.")

# ------------------- GUI -------------------
class DeployApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("Reverb Classifier — Model Deployment")
        self.geometry("700x380")
        self.configure(fg_color="#111113")

        self._build_ui()

    def _build_ui(self):
        title = ctk.CTkLabel(self, text="Deploy RT60 Classifier",
                             font=("Segoe UI Semibold", 22),
                             text_color="#00FF99")
        title.pack(pady=(20, 10))

        desc = ctk.CTkLabel(self, text="Classifies RT60 values in your Google Sheet into Dead Spot / Neutral Zone / Hot Spot.",
                            text_color="#cccccc", wraplength=580, justify="center")
        desc.pack(pady=(0, 20))

        frame = ctk.CTkFrame(self, fg_color="#1a1a1f", corner_radius=14)
        frame.pack(fill="x", padx=40, pady=(0, 20))

        # Google Sheet URL
        ctk.CTkLabel(frame, text="Google Sheet URL", text_color="#aaaaaa").grid(row=0, column=0, sticky="w", padx=12, pady=8)
        self.sheet_var = ctk.StringVar(value="https://docs.google.com/spreadsheets/d/12YI-C_c9Hmq-uzDdm9qrlsCrjmMmt7b4P0kJVjFM-98/edit?usp=sharing")
        ctk.CTkEntry(frame, textvariable=self.sheet_var, width=500,
                     fg_color="#111117", border_color="#00FF99").grid(row=0, column=1, padx=10, pady=8)

        # Service JSON
        ctk.CTkLabel(frame, text="Service Account JSON", text_color="#aaaaaa").grid(row=1, column=0, sticky="w", padx=12, pady=8)
        default_json = os.path.join(os.path.dirname(__file__), "projectdesignt6-b8c2872f2067.json")
        self.json_var = ctk.StringVar(value=default_json)
        ctk.CTkEntry(frame, textvariable=self.json_var, width=500,
                     fg_color="#111117", border_color="#00FF99").grid(row=1, column=1, padx=10, pady=8)

        # Layer selector (Sheet 1..Sheet 4)
        ctk.CTkLabel(frame, text="Layer (Sheet)", text_color="#aaaaaa").grid(row=2, column=0, sticky="w", padx=12, pady=8)
        self.layer_var = ctk.StringVar(value="1")
        self.layer_menu = ctk.CTkOptionMenu(frame, values=["1","2","3","4"], variable=self.layer_var, width=120)
        self.layer_menu.grid(row=2, column=1, sticky="w", padx=10, pady=8)

        # Deploy button
        self.deploy_btn = ctk.CTkButton(self, text="🚀 Deploy Model",
                                        command=self.deploy,
                                        fg_color="#00FF99", hover_color="#33FFB3",
                                        font=("Segoe UI Semibold", 18))
        self.deploy_btn.pack(pady=10)

        # Log
        self.log = ctk.CTkTextbox(self, height=100, fg_color="#0e0e12", text_color="#00FF99", 
                                  corner_radius=10, wrap="word")
        self.log.pack(fill="both", expand=True, padx=40, pady=(10, 20))
        self._write("Ready. Press 'Deploy Model' to classify RT60s in your sheet.\n")

    def _write(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.update_idletasks()

    def deploy(self):
        self._write("Connecting to Google Sheet...")
        try:
            # Connect to the requested worksheet (layer)
            ws = connect_sheet(self.sheet_var.get(), self.json_var.get())
            # Select worksheet based on Layer selector (support multiple layers)
            try:
                sheet_index = max(0, int(self.layer_var.get()) - 1)
            except Exception:
                sheet_index = 0
            try:
                import re
                m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", self.sheet_var.get())
                if m:
                    sheet_id = m.group(1)
                    from google.oauth2.service_account import Credentials as _Creds
                    creds = _Creds.from_service_account_file(self.json_var.get(), scopes=["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"])
                    client = gspread.authorize(creds)
                    sh = client.open_by_key(sheet_id)
                    sheets = sh.worksheets()
                    if sheet_index < 0:
                        sheet_index = 0
                    if sheet_index >= len(sheets):
                        for i in range(len(sheets), sheet_index + 1):
                            title = f"Sheet{i+1}"
                            sh.add_worksheet(title=title, rows=1000, cols=20)
                        sheets = sh.worksheets()
                    ws = sh.get_worksheet(sheet_index)
            except Exception as e:
                self._write(f"❌ Error selecting layer: {e}")
                raise
            self._write("Connected. Classifying RT60 values...")
            update_class_column(ws)
            self._write("✅ Classification complete. Sheet updated.")
        except Exception as e:
            self._write(f"❌ Error: {e}")
            messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    app = DeployApp()
    app.mainloop()
