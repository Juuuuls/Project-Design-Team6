"""reverberation Taker  (Option B with default Sheet link + robust JSON resolution)

Reads ultrasonic + RT60 data from Arduino (Amain.ino),
saves to CSV, and uploads results to an EXISTING Google Sheet
that you specify (default set below).

Expected Arduino line format: "<ultrasonic_cm>,<rt60_seconds>"
CSV header: number, Reverberation, Ultrasonic Value
"""

import argparse, subprocess, shutil, serial, csv, time, os, random, re
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# ---------- Arduino helpers ----------
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
        print("Upload complete. Waiting for Arduino to initialize...")
        time.sleep(3)
        return True
    except subprocess.CalledProcessError as e:
        print("Upload/compile failed:", e)
        return False

def _is_number(s: str) -> bool:
    try:
        float(str(s).strip())
        return True
    except Exception:
        return False

def generate_simulated_reading() -> str:
    ultrasonic = round(random.uniform(2.0, 400.0), 2)
    rt60 = round(random.uniform(0.10, 3.00), 3)
    return f"{ultrasonic},{rt60}"

# ---------- Google Sheets helpers ----------
def resolve_service_json(path_from_args: str) -> str | None:
    """
    Try to find a usable service-account JSON in common places:
      1) exact path passed via --service-json
      2) service_account.json next to this script
      3) GOOGLE_APPLICATION_CREDENTIALS environment variable
    Return a valid path or None if not found.
    """
    # 1) explicit argument
    if path_from_args and os.path.isfile(path_from_args):
        return path_from_args

    # 2) next to script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(script_dir, "service_account.json")
    if os.path.isfile(candidate):
        return candidate

    # 3) environment variable
    env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if env and os.path.isfile(env):
        return env

    return None

def upload_to_existing_sheet(csv_path, sheet_url, service_json):
    print("🔄 Uploading to existing Google Sheet...")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(service_json, scopes=scopes)
    client = gspread.authorize(creds)

    # Extract Sheet ID from URL
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", sheet_url)
    if not m:
        raise ValueError("Invalid Google Sheet URL – must contain /spreadsheets/d/<ID>")
    sheet_id = m.group(1)

    sh = client.open_by_key(sheet_id)
    ws = sh.sheet1  # change if you want a specific worksheet

    # Read local CSV and overwrite the sheet
    with open(csv_path, newline="") as f:
        rows = list(csv.reader(f))
    ws.clear()
    ws.update(rows)
    print(f"✅ Uploaded to {sheet_url}")

# ---------- Main ----------
def main():
    parser = argparse.ArgumentParser(description="Read ultrasonic + RT60 from Arduino and save to CSV + Google Sheet")

    # Serial / board
    parser.add_argument("--port", default="COM5")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--board", default="arduino:avr:uno")
    parser.add_argument("--sketch", default=r"C:\Users\Ju\OneDrive\Documents\Project_Design_I_Files\pYcODE\Amain\Amain.ino")

    # Capture / behavior
    parser.add_argument("--count", type=int, default=10, help="Rows to capture")
    parser.add_argument("--simulate", action="store_true", help="No serial; generate fake data")
    parser.add_argument("--no-upload", action="store_true", help="Skip arduino-cli compile/upload")
    parser.add_argument("--interval", type=float, default=3.0, help="Sim interval seconds between samples")

    # Files
    parser.add_argument("--out-dir", default=None, help="CSV output directory (default: script folder)")

    # Google Sheets
    parser.add_argument("--skip-gsheets", action="store_true", help="Do not upload to Google Sheets")
    # ✅ Updated default to your JSON path:
    parser.add_argument(
        "--service-json",
        default=r"C:\Users\Ju\OneDrive\Documents\Project_Design_I_Files\pYcODE\projectdesignt6-b8c2872f2067.json",
        help="Path to service account JSON (or set GOOGLE_APPLICATION_CREDENTIALS env var)"
    )
    parser.add_argument(
        "--sheet-link",
        default="https://docs.google.com/spreadsheets/d/12YI-C_c9Hmq-uzDdm9qrlsCrjmMmt7b4P0kJVjFM-98/edit?usp=sharing",
        help="Google Sheet link to upload the data"
    )

    args = parser.parse_args()

    if not args.no_upload and not args.simulate:
        try_upload(args.sketch, args.board, args.port)

    # Output paths
    out_dir = os.path.abspath(args.out_dir) if args.out_dir else os.path.dirname(os.path.abspath(__file__))
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(out_dir, f"peaks_{ts}.csv")

    header = ["number", "Reverberation", "Ultrasonic Value"]
    written = 0
    last_sim_time = time.time()

    # Serial open
    ser = None
    using_serial = not args.simulate
    if using_serial:
        try:
            ser = serial.Serial(args.port, args.baud, timeout=5)
            # settle/reset input
            try:
                ser.setDTR(False); time.sleep(0.4); ser.setDTR(True)
            except Exception:
                pass
            time.sleep(1.2)
            ser.reset_input_buffer()
            print(f"✅ Opened {args.port} @ {args.baud}")
        except Exception as e:
            print(f"⚠️ Serial port error: {e}\nSwitching to simulate mode.")
            using_serial = False

    # Capture + CSV save
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)

        while written < args.count:
            if using_serial:
                line = ser.readline().decode(errors="ignore").strip()
                if not line:
                    print("(waiting for data...)")
                    continue
            else:
                # Simulated pacing
                now = time.time()
                elapsed = now - last_sim_time
                if elapsed < args.interval:
                    time.sleep(args.interval - elapsed)
                last_sim_time = time.time()
                line = generate_simulated_reading()

            print("→", line)

            parts = [p.strip() for p in line.split(",")]
            # Expect exactly: ultrasonic,rt
            if len(parts) == 2 and _is_number(parts[0]) and _is_number(parts[1]):
                ultrasonic_val = float(parts[0])
                rt_val = float(parts[1])
                written += 1
                row = [str(written), f"{rt_val}", f"{ultrasonic_val}"]
                w.writerow(row)
                f.flush()

        if ser:
            try:
                ser.close()
            except Exception:
                pass

    print(f"✅ Saved {written} rows → {csv_path}")

    # Upload to your existing Google Sheet (if not skipped)
    if args.skip_gsheets:
        print("ℹ️ Skipping Google Sheets upload (--skip-gsheets set).")
        return

    sa_path = resolve_service_json(args.service_json)
    if not sa_path:
        print(
            "❌ Google Sheets upload skipped: Service account JSON not found.\n"
            "   Do one of the following and run again:\n"
            "   1) Pass --service-json \"C:\\path\\to\\service_account.json\"\n"
            "   2) Put service_account.json next to this script\n"
            "   3) Set env var GOOGLE_APPLICATION_CREDENTIALS to the JSON path\n"
            "   Also: share your Google Sheet with the service account email (Editor)."
        )
        return

    try:
        upload_to_existing_sheet(csv_path, args.sheet_link, sa_path)
    except Exception as e:
        print("❌ Google Sheets upload failed:", e)
        print("Tip: Ensure your Sheet is shared with the service account email (Editor access).")

if __name__ == "__main__":
    main()
