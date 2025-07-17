#!/usr/bin/env python3
import sys
import time
import pyvisa
import random
import re
import requests
import itertools
import threading
from datetime import datetime

COMMAND_FILE = "scpi_command_list.txt"
INDEX_FILE = "Rigol_MSO5000_SCPI_Indexes.txt"
COMMAND_DB_FILE = "Rigol_MSO5000_SCPI_Commands.txt"

SKIP_PATTERNS = ["WAV:DATA?", "DISPlay:DATA?"]
GREEN, YELLOW, RED, RESET = "\033[92m", "\033[93m", "\033[91m", "\033[0m"

def log(msg, color=RESET):
    print(f"{color}{msg}{RESET}")

def random_thinking():
    phrases = [
        "🐰 Pinky connected the probe... again.",
        "🧠 Brain says: 'We're going to interrogate every SCPI bit tonight, Pinky.'",
        "🔬 Amplifying neural SCPI harmonics...",
        "🎯 Targeting :CHANnel1 mindspace...",
        "👾 Spawning Pinky subprocess...",
        "☠️ Found residue from a failed command rebellion...",
        "💣 DOOM mode activated. Sending in BFG9000...",
        "📡 Listening to Rigol dreams...",
        "🔗 Unlocking forbidden opcodes...",
        "🛠️ Rebuilding command reality brick by byte...",
        "🍕 Pinky paused for a pizza. Brain not amused...",
        "🧪 Synthesizing new SCPI molecules in the lab...",
        "🎮 Pinky accidentally set trigger mode to NIGHTMARE.",
        "📟 Trying :BUS4:RS232:PEND? while whistling the DOOM theme...",
        "🌀 Brain is calculating 12-dimensional SCPI vectors...",
        "🔐 Attempting to picklock :SYSTem:SECure?", 
        "🐰 Pinky asked the scope politely. It responded with a beep.",
        "🧠 Brain is building a recursive command parser... with crayons.",
        "👣 Tracing SCPI breadcrumbs through the logic analyzer."
    ]
    if random.random() < 0.5:
        log(random.choice(phrases), YELLOW)

def load_commands():
    try:
        with open(COMMAND_FILE, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        log("❌ scpi_command_list.txt not found", RED)
        sys.exit(1)

def load_all_commands():
    cmds = set(load_commands())
    try:
        with open("learned_scpi_commands_latest.txt", "r") as f:
            learned = [line.strip() for line in f if line.strip()]
            cmds.update(learned)
            log(f"➕ Included {len(learned)} learned commands", YELLOW)
    except FileNotFoundError:
        pass
    return sorted(cmds)

def load_known_scpi_db():
    try:
        with open(COMMAND_DB_FILE, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def load_index_info():
    info = {}
    try:
        with open(INDEX_FILE, "r") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 4:
                    key = parts[0].strip()
                    direction = parts[2].strip()
                    values = parts[3:]
                    info.setdefault(key, {}).setdefault(direction, []).extend(values)
    except FileNotFoundError:
        pass
    return info

def list_devices():
    rm = pyvisa.ResourceManager()
    res = rm.list_resources()
    log("🔎 VISA Resources:")
    for r in res:
        print(f"  - {r}")
    if not res:
        log("❌ No VISA devices found.", RED)

def connect(resource_str):
    rm = pyvisa.ResourceManager()
    try:
        scope = rm.open_resource(resource_str)
        scope.timeout = 5000
        scope.chunk_size = 102400
        idn = scope.query("*IDN?")
        log(f"✅ Connected: {idn}", GREEN)
        return scope
    except Exception as e:
        log(f"❌ Connection failed: {e}", RED)
        return None

def test_all(scope):
    cmds = load_all_commands()
    results = []
    for i, cmd in enumerate(cmds, 1):
        try:
            r = scope.query(cmd).strip()
            res = f"✅ {r}" if r else "⚠️ Empty"
        except Exception as e:
            res = f"❌ {e}"
        results.append((cmd, res))
        log(f"▶ [{i}/{len(cmds)}] {cmd:<40} → {res}", GREEN if '✅' in res else RED if '❌' in res else YELLOW)
    save_log("test_all", results)

def test_group(scope, prefix):
    cmds = [c for c in load_all_commands() if c.startswith(f":{prefix.upper()}")]
    if not cmds:
        log(f"❌ No commands found for group '{prefix}'", RED)
        return
    results = []
    for i, cmd in enumerate(cmds, 1):
        try:
            r = scope.query(cmd).strip()
            res = f"✅ {r}" if r else "⚠️ Empty"
        except Exception as e:
            res = f"❌ {e}"
        results.append((cmd, res))
        log(f"▶ [{i}/{len(cmds)}] {cmd:<40} → {res}", GREEN if '✅' in res else RED if '❌' in res else YELLOW)
    save_log(f"group_{prefix}", results)

def query_licenses(ip):
    try:
        url = f"http://{ip}/cgi-bin/options.cgi"
        res = requests.post(url, timeout=3)
        if res.status_code != 200:
            log(f"❌ HTTP {res.status_code} from Rigol", RED)
            return
        options = res.text.strip().split('#')
        for item in options:
            parts = item.split('$')
            if len(parts) == 3:
                code, status, desc = parts
                log(f"{code.strip():<10} → {status.strip():<5}  {desc.strip()}", GREEN if status.strip() == "1" else YELLOW)
    except Exception as e:
        log(f"❌ License query failed: {e}", RED)

def run_waveform_test(scope, channel="CHAN1"):
    try:
        scope.write(":WAV:FORM BYTE")
        scope.write(":WAV:MODE NORM")
        scope.write(":WAV:POIN:MODE RAW")
        scope.write(f":WAV:POIN 1200")
        scope.write(f":WAV:SOUR {channel}")
        time.sleep(0.2)
        pre = scope.query(":WAV:PRE?").split(",")
        raw = scope.query_binary_values(":WAV:DATA?", datatype='B')
        log(f"✅ Got {len(raw)} bytes from {channel}", GREEN)
    except Exception as e:
        log(f"❌ Waveform read error: {e}", RED)

def fuzz_scope(scope, attempts=50):
    results = []
    for i in range(attempts):
        cmd = ":" + ":".join([
            random.choice(["CHANnel1", "MATH1", "BUS1", "TRIGger", "DISPlay", "WAVeform"]),
            random.choice(["SCALe", "OFFSet", "COUPling", "STATus", "GRADing", "FORM", "SOURce"]),
        ]) + "?"
        try:
            r = scope.query(cmd).strip()
            res = f"✅ {r}" if r else "⚠️ Empty"
        except Exception as e:
            res = f"❌ {e}"
        results.append((cmd, res))
        log(f"⚙️  {cmd:<40} → {res}", GREEN if '✅' in res else RED if '❌' in res else YELLOW)
    save_log("fuzz", results)

def learn_scope(scope, attempts=100):
    known = set(load_all_commands())
    discovered = []
    pinky_logged = False

    try:
        for _ in range(attempts):
            cmd = ":" + ":".join([
                random.choice(["CHANnel1", "MATH1", "BUS1", "TRIGger", "DISPlay", "WAVeform", "MEASure", "TIMebase", "SYSTem"]),
                random.choice(["SCALe", "OFFSet", "COUPling", "STATus", "GRADing", "FORM", "SOURce", "OPERator", "MODE", "TYPE"])
            ]) + "?"
            if cmd in known or cmd in [d[0] for d in discovered]:
                continue
            try:
                r = scope.query(cmd).strip()
                if r:
                    discovered.append((cmd, r))
                    log(f"🧠 Learned: {cmd} → {r}", GREEN)
            except Exception:
                continue

            if not pinky_logged:
                log("🐰 Pinky connected the probe... again.", YELLOW)
                pinky_logged = True
            else:
                random_thinking()

    except KeyboardInterrupt:
        log("\n🛑 Learning interrupted by user (Ctrl+C)", RED)

    if discovered:
        timestamped = f"learned_scpi_commands_{datetime.now():%Y%m%d_%H%M%S}.txt"
        latest = "learned_scpi_commands_latest.txt"
        with open(timestamped, "w") as f1, open(latest, "w") as f2:
            for cmd, _ in discovered:
                f1.write(cmd + "\n")
                f2.write(cmd + "\n")
        log(f"💾 Learned {len(discovered)} new commands → {timestamped}", GREEN)
        log(f"📌 Updated latest discoveries → {latest}", YELLOW)
    else:
        log("🤷 Nothing new discovered.", YELLOW)

def save_log(name, results):
    fname = f"doom2_log_{name}_{datetime.now():%Y%m%d_%H%M%S}.txt"
    with open(fname, "w") as f:
        for cmd, result in results:
            f.write(f"{cmd:<40} → {result}\n")
    log(f"💾 Saved log to {fname}", GREEN)

def find_usb():
    rm = pyvisa.ResourceManager()
    usb_list = [r for r in rm.list_resources() if "USB" in r]
    if not usb_list:
        log("❌ No USB scopes found", RED)
        sys.exit(1)
    return usb_list[0]

def resolve_scope(argv):
    if "--ip" in argv:
        idx = argv.index("--ip")
        if idx + 1 < len(argv):
            return f"TCPIP0::{argv[idx+1]}::INSTR"
        else:
            log("❌ Missing IP after --ip", RED)
            sys.exit(1)
    elif "--usb" in argv:
        return find_usb()
    else:
        log("❌ Specify --ip <addr> or --usb", RED)
        sys.exit(1)

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  doom2 list")
        print("  doom2 test --ip <addr> | --usb")
        print("  doom2 group MATH1 --ip <addr> | --usb")
        print("  doom2 licenses <ip>")
        print("  doom2 waveform CHAN1 --ip <addr> | --usb")
        print("  doom2 fuzz --ip <addr> | --usb")
        print("  doom2 learn --ip <addr> | --usb")
        return

    mode = sys.argv[1].lower()

    if mode == "list":
        list_devices()
    elif mode == "licenses":
        if len(sys.argv) < 3:
            log("❌ IP required", RED)
        else:
            query_licenses(sys.argv[2])
    elif mode == "test":
        scope = connect(resolve_scope(sys.argv))
        if scope:
            test_all(scope)
            scope.close()
    elif mode == "group":
        if len(sys.argv) < 3:
            log("❌ Group name required", RED)
            return
        scope = connect(resolve_scope(sys.argv))
        if scope:
            test_group(scope, sys.argv[2])
            scope.close()
    elif mode == "waveform":
        scope = connect(resolve_scope(sys.argv))
        if scope:
            run_waveform_test(scope, sys.argv[2] if len(sys.argv) > 2 else "CHAN1")
            scope.close()
    elif mode == "fuzz":
        scope = connect(resolve_scope(sys.argv))
        if scope:
            fuzz_scope(scope)
            scope.close()
    elif mode == "learn":
        scope = connect(resolve_scope(sys.argv))
        if scope:
            learn_scope(scope)
            scope.close()
    else:
        log("❌ Unknown command", RED)

if __name__ == "__main__":
    main()
