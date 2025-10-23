# datagatherer_po2_g.py
"""
Reverberation Taker (Angle IDs + Google Sheet + Prediction)
Outputs EXACT columns: angle, rt60, utv, class

Input line format from Arduino: "<ultrasonic_cm>,<rt60_seconds>"
Angle IDs: 0..355 step 5 (configurable)
Prediction: loads joblib model (if provided) and writes label to 'class'
"""

import argparse, subprocess, shutil, serial, csv, time, os, random, re
from datetime import datetime
import joblib

# Optional: Google Sheets
import gspread
from google.oauth2.service_account import Credentials

# ---------------- Arduino helpers ----------------
def has_arduino_cli() -> bool:
    return shutil.which("arduino-cli") is not None

def try_upload(sketch_path: str, board: str, port: str) -> bool:
    if not has_arduino_cli():
        print("arduino-cli not found in PATH; skipping upload.")
        return False
    try:
        print("Compiling sketch...")
        subprocess.run(["arduino-cli", "compile", "--fqbn", board, sketch_path], check=True)
        print("Uploading sketch...")
        subprocess.run(["arduino-cli", "upload", "-p", port, "--fqbn", board, sketch_path], check=True)
        print("Upload complete. Waiting for Arduino to reset…")
        time.sleep(3)
        return True
    except subprocess.CalledProcessError as e:
        print("Upload/compile failed:", e)
        return False

def _is_number(s: str) -> bool:
    try:
        float(str(s).strip()); return True
    except Exception:
        return False

def generate_simulated_reading() -> str:
    ultrasonic = round(random.uniform(2.0, 400.0), 2)
    rt60 = round(random.uniform(0.10, 3.00), 3)
    return f"{ultrasonic},{rt60}"

# ---------------- Google Sheets helpers ----------------
def resolve_service_json(path_from_args: str) -> str | None:
    if path_from_args and os.path.isfile(path_from_args):
        return path_from_args
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(script_dir, "service_account.json")
    if os.path.isfile(candidate):
        return candidate
    env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if env and os.path.isfile(env):
        return env
    return None

def upload_to_existing_sheet(csv_path, sheet_url, service_json):
    print("🔄 Uploading to existing Google Sheet…")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(service_json, scopes=scopes)
    client = gspread.authorize(creds)

    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", sheet_url)
    if not m:
        raise ValueError("Invalid Google Sheet URL – must contain /spreadsheets/d/<ID>")
    sheet_id = m.group(1)

    sh = client.open_by_key(sheet_id)
    ws = sh.sheet1

    with open(csv_path, newline="") as f:
        rows = list(csv.reader(f))
    ws.clear()
    ws.update(rows)
    print(f"✅ Uploaded to {sheet_url}")

# ---------------- Prediction ----------------
class ZonePredictor:
    """
    Loads a joblib bundle with:
      - model: fitted classifier
      - feature_order: e.g. ["frequency","RT60","RT60_deviation"]
    """
    def __init__(self, model_path: str, default_frequency: float = 1000.0):
        self.enabled = False
        self.default_frequency = float(default_frequency)
        self.feature_order = ["frequency","RT60","RT60_deviation"]
        if not model_path or not os.path.isfile(model_path):
            print("ZonePredictor: model not provided/found. Classification will be blank.")
            return
        try:
            bundle = joblib.load(model_path)
            self.model = bundle["model"]
            self.feature_order = bundle.get("feature_order", self.feature_order)
            self.enabled = True
            print(f"✅ Zone model loaded: {model_path}")
            print(f"   Features: {self.feature_order}")
        except Exception as e:
            print("ZonePredictor: failed to load model:", e)

    def predict(self, rt60: float, frequency: float | None = None) -> str:
        if not self.enabled:
            return ""
        if frequency is None:
            frequency = self.default_frequency
        rt60_dev = abs(float(rt60) - 0.3)
        feats = {
            "frequency": float(frequency),
            "RT60": float(rt60),
            "RT60_deviation": float(rt60_dev),
        }
        row = [[feats[k] for k in self.feature_order]]
        try:
            pred = self.model.predict(row)[0]
            return str(pred)
        except Exception:
            return ""

# ---------------- Main ----------------
def main():
    parser = argparse.ArgumentParser(description="Read ultrasonic+RT60 → CSV (angle IDs) → Google Sheet (optional)")

    # Serial / board
    parser.add_argument("--port", default="COM5")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--board", default="arduino:avr:uno")
    parser.add_argument("--sketch", default=r"C:\Users\Ju\OneDrive\Documents\Project_Design_I_Files\pYcODE2\Amain\Amain.ino")

    # Angle / timing
    parser.add_argument("--max-angle", type=int, default=355)
    parser.add_argument("--angle-step", type=int, default=5)
    parser.add_argument("--angle-speed", type=int, choices=[1,5], default=5)
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--interval", type=float, default=None)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--no-upload", action="store_true")

    # Files
    parser.add_argument("--out-dir", default=None)

    # Google Sheets
    parser.add_argument("--skip-gsheets", action="store_true")
    parser.add_argument("--service-json",
        default=r"C:\Users\Ju\OneDrive\Documents\Project_Design_I_Files\pYcODE2\projectdesignt6-b8c2872f2067.json")
    parser.add_argument("--sheet-link",
        default="https://docs.google.com/spreadsheets/d/12YI-C_c9Hmq-uzDdm9qrlsCrjmMmt7b4P0kJVjFM-98/edit?usp=sharing")

    # Prediction
    parser.add_argument("--model-path",
        default=r"C:\Users\Ju\OneDrive\Documents\Project_Design_I_Files\pYcODE2\reverb_zone_rf.joblib")
    parser.add_argument("--freq", type=float, default=1000.0)
    parser.add_argument("--no-predict", action="store_true")

    args = parser.parse_args()

    # compile/upload if desired
    if not args.no_upload and not args.simulate:
        try_upload(args.sketch, args.board, args.port)

    # derive angle IDs
    angle_ids = list(range(0, args.max_angle + 1, args.angle_step))  # 0,5,...,355
    max_rows = len(angle_ids)  # 72 by default
    rows_needed = args.count if (args.count and args.count > 0) else max_rows
    rows_needed = min(rows_needed, max_rows)

    # interval default = step/speed
    interval = args.interval if (args.interval and args.interval > 0) else (args.angle_step / args.angle_speed)

    # predictor
    predictor = ZonePredictor(args.model_path, default_frequency=args.freq)
    do_predict = predictor.enabled and (not args.no_predict)

    # output
    out_dir = os.path.abspath(args.out_dir) if args.out_dir else os.path.dirname(os.path.abspath(__file__))
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(out_dir, f"peaks_{ts}.csv")

    # ======= HEADER EXACTLY AS REQUESTED =======
    header = ["angle", "rt60", "utv", "class"]

    written = 0
    last_time = time.time()

    # serial
    ser = None
    using_serial = not args.simulate
    if using_serial:
        try:
            ser = serial.Serial(args.port, args.baud, timeout=5)
            try:
                ser.setDTR(False); time.sleep(0.4); ser.setDTR(True)
            except Exception:
                pass
            time.sleep(1.2)
            ser.reset_input_buffer()
            print(f"✅ Opened {args.port} @ {args.baud}")
        except Exception as e:
            print(f"⚠️ Serial open failed: {e} → Simulate mode")
            using_serial = False

    print(f"Angle IDs: 0..{args.max_angle} step {args.angle_step}  → max rows {max_rows}")
    print(f"Angle speed: {args.angle_speed}°/s  → interval {interval:.3f}s per row")
    print(f"Target rows this run: {rows_needed}")
    if do_predict:
        print("🔮 Zone prediction ENABLED")

    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)

        for idx in range(rows_needed):
            angle_id = angle_ids[idx]

            # timing control
            now = time.time()
            elapsed = now - last_time
            if elapsed < interval:
                time.sleep(interval - elapsed)
            last_time = time.time()

            # read one line (ultrasonic, rt60)
            if using_serial:
                line = ser.readline().decode(errors="ignore").strip()
                if not line:
                    print("(waiting for data…)"); continue
            else:
                line = generate_simulated_reading()

            print(f"→ {angle_id}: {line}")

            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 2 and _is_number(parts[0]) and _is_number(parts[1]):
                utv = float(parts[0])      # ultrasonic cm
                rt60 = float(parts[1])     # seconds

                label = predictor.predict(rt60=rt60, frequency=args.freq) if do_predict else ""

                # ======= ROW EXACTLY AS REQUESTED =======
                row = [str(angle_id), f"{rt60}", f"{utv}", label]
                w.writerow(row); f.flush()
                written += 1
            else:
                print(f"(unparsed) {line} — skipped")

    if ser:
        try: ser.close()
        except Exception: pass

    print(f"✅ Saved {written} rows → {csv_path}")

    # Google Sheets
    if args.skip_gsheets:
        print("ℹ️ Skipping Google Sheets upload (--skip-gsheets).")
        return
    sa_path = resolve_service_json(args.service_json)
    if not sa_path:
        print("❌ Sheets upload skipped: service-account JSON not found.")
        return

    try:
        upload_to_existing_sheet(csv_path, args.sheet_link, sa_path)
    except Exception as e:
        print("❌ Google Sheets upload failed:", e)
        print("Tip: share your Sheet with the service account email (Editor).")

if __name__ == "__main__":
    main()
