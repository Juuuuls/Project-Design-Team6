"""reverberation Taker

Reads ultrasonic + RT60 from Arduino (Amain.ino) and saves to CSV.
Expected Arduino line format per sample: "<ultrasonic_cm>,<rt60_seconds>"
CSV header: number, Reverberation, Ultrasonic Value
"""

import argparse
import subprocess
import shutil
import serial
import csv
import time
import os
import random
from datetime import datetime

# ---------- Helpers ----------
def has_arduino_cli() -> bool:
    return shutil.which("arduino-cli") is not None

def try_upload(sketch_path: str, board: str, port: str) -> bool:
    """Compile and upload with arduino-cli if available."""
    if not has_arduino_cli():
        print("arduino-cli not found in PATH; skipping upload.")
        return False
    try:
        print("Compiling sketch...")
        subprocess.run(
            ["arduino-cli", "compile", "--fqbn", board, sketch_path],
            check=True
        )
        print("Uploading sketch...")
        subprocess.run(
            ["arduino-cli", "upload", "-p", port, "--fqbn", board, sketch_path],
            check=True
        )
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
    """Simulate the Amain.ino output: ultrasonic(cm),rt60(seconds)."""
    ultrasonic = round(random.uniform(2.0, 400.0), 2)
    rt60 = round(random.uniform(0.10, 3.00), 3)
    return f"{ultrasonic},{rt60}"

# ---------- Main ----------
def main():
    parser = argparse.ArgumentParser(description="Read ultrasonic + RT60 from Arduino and save to CSV")
    parser.add_argument("--port", default="COM5", help="Arduino serial port (e.g. COM5 or /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=9600, help="Serial baud rate (must match sketch)")
    # Hardcoded to your Amain.ino path:
    parser.add_argument(
        "--sketch",
        default=r"C:\Users\Ju\OneDrive\Documents\Project_Design_I_Files\pYcODE\Amain\Amain.ino",
        help="Path to Amain.ino"
    )
    parser.add_argument("--board", default="arduino:avr:uno", help="FQBN for arduino-cli (e.g. arduino:avr:uno)")
    parser.add_argument("--count", type=int, default=10, help="Number of rows to write")
    parser.add_argument("--no-upload", action="store_true", help="Skip compile/upload via arduino-cli")
    parser.add_argument("--simulate", action="store_true", help="Generate fake data instead of reading serial")
    parser.add_argument("--interval", type=float, default=3.0, help="Simulate: seconds between samples")
    parser.add_argument("--out-dir", default=None, help="Directory to save CSV (defaults to this script's folder)")
    parser.add_argument("--require-serial", action="store_true", help="Exit if serial cannot be opened")
    parser.add_argument("--debug-raw", action="store_true", help="Write raw lines to a log file in out-dir")
    args = parser.parse_args()

    rows_needed = max(1, args.count)

    if not args.no_upload and not args.simulate:
        try_upload(args.sketch, args.board, args.port)

    # Output paths
    out_dir = os.path.abspath(args.out_dir) if args.out_dir else os.path.dirname(os.path.abspath(__file__))
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(out_dir, f"peaks_{ts}.csv")
    log_path = os.path.join(out_dir, f"raw_{ts}.log") if args.debug_raw else None

    print(f"Saving to: {csv_path}")

    # Serial setup
    ser = None
    using_serial = False
    if not args.simulate:
        try:
            # Longer timeout to accommodate ~3s cadence
            ser = serial.Serial(args.port, args.baud, timeout=5)
            # Give Arduino time to reset and stabilize
            try:
                ser.setDTR(False)
                time.sleep(0.4)
                ser.setDTR(True)
            except Exception:
                pass
            time.sleep(1.2)
            ser.reset_input_buffer()
            using_serial = True
            print(f"✅ Opened {args.port} @ {args.baud}")
        except Exception as e:
            print(f"Could not open serial port {args.port}: {e}")
            if args.require_serial:
                print("--require-serial is set; exiting.")
                return
            print("Falling back to simulate mode (use --no-upload to skip Arduino upload next time).")
            using_serial = False
            args.simulate = True  # force simulate pathway

    written = 0
    last_sim_time = time.time()

    try:
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            # Header as requested
            w.writerow(["number", "Reverberation", "Ultrasonic Value"])
            try:
                f.flush(); os.fsync(f.fileno())
            except Exception:
                pass

            while written < rows_needed:
                # Read or simulate one line
                if using_serial:
                    try:
                        raw = ser.readline()
                        if not raw:
                            print("(waiting for data...)")
                            continue
                        line = raw.decode(errors="ignore").strip()
                    except Exception as e:
                        print(f"Serial read error: {e}")
                        if args.require_serial:
                            print("--require-serial is set; exiting.")
                            break
                        line = generate_simulated_reading()
                else:
                    # Simulated pacing
                    now = time.time()
                    elapsed = now - last_sim_time
                    if elapsed < args.interval:
                        time.sleep(args.interval - elapsed)
                    last_sim_time = time.time()
                    line = generate_simulated_reading()

                # Optional debug log
                if args.debug_raw and log_path:
                    try:
                        with open(log_path, "a", encoding="utf-8") as dbg:
                            dbg.write(f"{datetime.now().isoformat()} RAW: {line}\n")
                    except Exception:
                        pass
                else:
                    # lightweight heartbeat
                    print(f"→ {line}")

                # Skip header-ish lines from the sketch, if any
                lower = line.lower()
                if lower.startswith("ultrasonic") or lower.startswith("distance") or lower.startswith("rt"):
                    continue

                # Expect: ultrasonic,rt
                parts = [p.strip() for p in line.split(",")]
                if len(parts) == 2 and _is_number(parts[0]) and _is_number(parts[1]):
                    ultrasonic_val = float(parts[0])
                    rt_val = float(parts[1])  # seconds
                    written += 1
                    w.writerow([str(written), f"{rt_val}", f"{ultrasonic_val}"])
                    try:
                        f.flush(); os.fsync(f.fileno())
                    except Exception:
                        pass
                    continue

                # Ignore anything else (units in-line, partials, noise, etc.)

    except KeyboardInterrupt:
        print("Stopped by user.")
    except Exception as e:
        print("Error while recording:", e)
    finally:
        if ser is not None and ser.is_open:
            try:
                ser.close()
            except Exception:
                pass

    print(f"✅ Done! Collected {written} rows → {csv_path}")

if __name__ == "__main__":
    main()
