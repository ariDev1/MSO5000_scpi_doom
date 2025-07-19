#!/usr/bin/env python3
import sys
import time
import pyvisa
import random
import re
import requests
import itertools
import threading
import readline
import rlcompleter
import csv
from datetime import datetime
from pinky_quotes import phrases

COMMAND_FILE = "scpi_command_list.txt"
INDEX_FILE = "Rigol_MSO5000_SCPI_Indexes.txt"
COMMAND_DB_FILE = "Rigol_MSO5000_SCPI_Commands.txt"

POWER_QUALITY_GUESSES = [
    "VRMS?", "IRMS?", "THD?", "CREST?", "FACTOR?", "FREQ?", "WATT?", "RIPPle?",
    "PF?", "REAL?", "REACtive?", "APPArent?", "SAG?", "ANGLE?", "PHASes?",
    "VOLTage?", "CURRent?", "VALue?", "ALL?", "ENERgy?", "CALCulate?", "STATe?"
]

SKIP_PATTERNS = ["WAV:DATA?", "DISPlay:DATA?"]
GREEN, YELLOW, RED, RESET = "\033[92m", "\033[93m", "\033[91m", "\033[0m"
DRY_RUN = "--dry-run" in sys.argv

def build_scpi_tree(filename="scpi_command_list.txt"):
    tree = {}
    try:
        with open(filename, "r") as f:
            for line in f:
                parts = line.strip().strip(":").split(":")
                node = tree
                for part in parts:
                    part = part.upper()
                    node = node.setdefault(part, {})
    except FileNotFoundError:
        log(f"❌ SCPI command list file not found: {filename}", RED)
        return {}
    return tree

def load_wordlist(path):
    try:
        with open(path, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        log(f"❌ Failed to load wordlist: {e}", RED)
        return []

def log(msg, color=RESET):
    print(f"{color}{msg}{RESET}")

def random_thinking():
    if random.random() < 0.5:
        log(random.choice(phrases), YELLOW)

def load_commands():
    try:
        with open(COMMAND_FILE, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        log("❌ scpi_command_list.txt not found", RED)
        sys.exit(1)

def load_all_commands(idn=None):
    cmds = set(load_commands())
    if idn:
        tag = idn.replace(',', '_').replace(' ', '_').replace('.', '_').strip()
        learned_file = f"learned_scpi_latest_{tag}.txt"
    else:
        learned_file = "learned_scpi_commands_latest.txt"

    try:
        with open(learned_file, "r") as f:
            learned = [line.strip() for line in f if line.strip()]
            cmds.update(learned)
            log(f"➕ Included {len(learned)} learned commands from {learned_file}", YELLOW)
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
        return scope, idn
    except Exception as e:
        log(f"❌ Connection failed: {e}", RED)
        return None, None

def test_all(scope, idn=None):
    cmds = load_all_commands(idn=idn)
    results = []
    for i, cmd in enumerate(cmds, 1):
        cmd = cmd.strip()
        if any(skip in cmd for skip in SKIP_PATTERNS):
            log(f"⏭️ Skipped {cmd}", YELLOW)
            continue
        try:
            if DRY_RUN:
                res = "💤 (dry-run)"
            else:
                r = scope.query(cmd).strip()
                res = f"✅ {r}" if r else "⚠️ Empty"
        except Exception as e:
            res = f"❌ {e}"
        results.append((cmd, res))
        log(f"▶ [{i}/{len(cmds)}] {cmd:<40} → {res}", GREEN if '✅' in res else RED if '❌' in res else YELLOW)
    save_log("test_all", results, idn=idn)

def test_group(scope, prefix, idn=None):
    cmds = [c for c in load_all_commands() if c.startswith(f":{prefix.upper()}")]
    if not cmds:
        log(f"❌ No commands found for group '{prefix}'", RED)
        return
    results = []
    for i, cmd in enumerate(cmds, 1):
        cmd = cmd.strip()
        if any(skip in cmd for skip in SKIP_PATTERNS):
            log(f"⏭️ Skipped {cmd}", YELLOW)
            continue
        try:
            if DRY_RUN:
                res = "💤 (dry-run)"
            else:
                r = scope.query(cmd).strip()
                res = f"✅ {r}" if r else "⚠️ Empty"
        except Exception as e:
            res = f"❌ {e}"
        results.append((cmd, res))
        log(f"▶ [{i}/{len(cmds)}] {cmd:<40} → {res}", GREEN if '✅' in res else RED if '❌' in res else YELLOW)
    save_log(f"group_{prefix}", results, idn=idn)

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

def fuzz_scope(scope, idn=None, attempts=50):
    results = []
    try:
        for i in range(attempts):
            cmd = ":" + ":".join([
                random.choice(["CHANnel1", "MATH1", "BUS1", "TRIGger", "DISPlay", "WAVeform"]),
                random.choice(["SCALe", "OFFSet", "COUPling", "STATus", "GRADing", "FORM", "SOURce"]),
            ]) + "?"
            try:
                if DRY_RUN:
                    res = "💤 (dry-run)"
                else:
                    r = scope.query(cmd).strip()
                    res = f"✅ {r}" if r else "⚠️ Empty"
            except Exception as e:
                res = f"❌ {e}"
            results.append((cmd, res))
            log(f"⚙️  {cmd:<40} → {res}", GREEN if '✅' in res else RED if '❌' in res else YELLOW)
    
    except KeyboardInterrupt:
        log("\n🛑 FUZZ interrupted by user (Ctrl+C)", RED)
    
    save_log("fuzz", results, idn=idn)

def learn_scope(scope, idn=None, attempts=100, prefix=None):
    known = set(load_all_commands())
    discovered = []
    pinky_logged = False

    try:
        for _ in range(attempts):
            if prefix:
                cmd_root = prefix.strip(":").upper()
            else:
                cmd_root = random.choice([
                    "CHANnel1", "MATH1", "BUS1", "TRIGger", "DISPlay",
                    "WAVeform", "MEASure", "TIMebase", "SYSTem", "POWer"
                ])

            subcmd = random.choice([
                "SCALe", "OFFSet", "COUPling", "STATus", "GRADing", "FORM",
                "SOURce", "OPERator", "MODE", "TYPE", "DISPlay", "REFLevel",
                "QUALity", "RIPPle"
            ])
            cmd = f":{cmd_root}:{subcmd}?"

            if cmd in known or cmd in [d[0] for d in discovered] or any(skip in cmd for skip in SKIP_PATTERNS):
                continue

            try:
                if DRY_RUN:
                    discovered.append((cmd, "💤 (dry-run)"))
                    log(f"🧠 Would test: {cmd}", YELLOW)
                else:
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
        tag = idn.replace(',', '_').replace(' ', '_').replace('.', '_').strip() if idn else "unknown"
        timestamped = f"learned_scpi_{tag}_{datetime.now():%Y%m%d_%H%M%S}.txt"
        latest = f"learned_scpi_latest_{tag}.txt"
        with open(timestamped, "w") as f1, open(latest, "w") as f2:
            for cmd, _ in discovered:
                f1.write(cmd.strip() + "\n")
                f2.write(cmd.strip() + "\n")
        log(f"💾 Learned {len(discovered)} new commands → {timestamped}", GREEN)
        log(f"📌 Updated latest discoveries → {latest}", YELLOW)
    else:
        log("🤷 Nothing new discovered.", YELLOW)

def smart_learn_scope(scope, idn=None, prefix=None):
    known = set(load_all_commands())
    discovered = []
    pinky_logged = False

    tree = build_scpi_tree()
    prefix_parts = [p.upper() for p in prefix.strip(":").split(":")] if prefix else []

    # Navigate to subtree
    node = tree
    for part in prefix_parts:
        node = node.get(part, {})
    if not node:
        log(f"❌ Prefix not found in SCPI tree: {prefix}", RED)
        return

    # Seed guesses from current node
    guess_suffixes = [
        "MODE?", "SOURce?", "FORMat?", "STATus?", "ENABle?", "TYPE?", "SCALe?",
        "OFFSet?", "COUPling?", "OPERator?", "DISPlay?", "RIPPle?", "PERCent?",
        "ABSolute?", "LOW?", "HIGH?", "MID?", "FREQreference?", "QUALity?",
        "QUALity:DISPlay?", "QUALity:STATe?", "QUALity:VALue?",
        "QUALity:ALL?", "QUALity:VOLTage?", "QUALity:CURRent?", "QUALity:THD?",
        "QUALity:WATTs?", "QUALity:FACTOR?", "QUALity:FREQ?", "QUALity:HARMonics?",
        "QUALity:CREST?", "QUALity:VRMS?", "QUALity:IRMS?", "QUALity:PF?", "QUALity:PHASes?"
    ]

    # Work queue of paths (like BFS)
    from collections import deque
    queue = deque()
    queue.append((prefix_parts, node))

    seen = set()

    try:
        while queue:
            base_path, current_node = queue.popleft()
            base_cmd = ":" + ":".join(base_path)

            # Guess deeper subcommands
            for suffix in guess_suffixes:
                trial = base_cmd + ":" + suffix
                trial = trial.replace("::", ":")  # just in case

                if trial in known or trial in seen or any(skip in trial for skip in SKIP_PATTERNS):
                    continue
                seen.add(trial)

                try:
                    if DRY_RUN:
                        discovered.append((trial, "💤 (dry-run)"))
                        log(f"🧠 Would test: {trial}", YELLOW)
                    else:
                        r = scope.query(trial).strip()
                        if r:
                            discovered.append((trial, r))
                            log(f"🧠 Learned: {trial} → {r}", GREEN)

                            # If valid, also try to go deeper
                            part = suffix.rstrip("?").upper()
                            queue.append((base_path + [part], {}))
                except Exception:
                    continue

                if not pinky_logged:
                    log("🐰 Pinky connected the probe... again.", YELLOW)
                    pinky_logged = True
                else:
                    random_thinking()

    except KeyboardInterrupt:
        log("\n🛑 Smart learning interrupted by user (Ctrl+C)", RED)

    if discovered:
        tag = idn.replace(',', '_').replace(' ', '_').replace('.', '_').strip() if idn else "unknown"
        timestamped = f"learned_scpi_{tag}_{datetime.now():%Y%m%d_%H%M%S}.txt"
        latest = f"learned_scpi_latest_{tag}.txt"
        with open(timestamped, "w") as f1, open(latest, "w") as f2:
            for cmd, _ in discovered:
                f1.write(cmd.strip() + "\n")
                f2.write(cmd.strip() + "\n")
        log(f"💾 Smart-learned {len(discovered)} new commands → {timestamped}", GREEN)
        log(f"📌 Updated latest discoveries → {latest}", YELLOW)
    else:
        log("🤷 No new commands discovered.", YELLOW)

def focus_probe(scope, idn=None, prefix=":POWer:QUALity:", wordlist=None):
    if "--wordlist" in sys.argv:
        try:
            idx = sys.argv.index("--wordlist")
            wordlist_path = sys.argv[idx + 1]
            wordlist = load_wordlist(wordlist_path)
            log(f"📖 Loaded wordlist with {len(wordlist)} entries from {wordlist_path}", GREEN)
        except Exception as e:
            log(f"❌ Invalid --wordlist usage: {e}", RED)
            return

    if wordlist is None:
        wordlist = POWER_QUALITY_GUESSES

    known = set(load_all_commands())
    discovered = []
    pinky_logged = False
    seen = set()

    csv_file = None
    if "--save-csv" in sys.argv:
        csv_name = f"focus_results_{datetime.now():%Y%m%d_%H%M%S}.csv"
        csv_file = open(csv_name, "w", newline="")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["Command", "Response"])

    depth = 1
    if "--depth" in sys.argv:
        try:
            depth = int(sys.argv[sys.argv.index("--depth") + 1])
        except:
            log("⚠️ Invalid depth value, using default = 1", YELLOW)

    try:
        for suffix in wordlist:
            cmd = prefix.rstrip(":") + ":" + suffix
            if cmd in known or cmd in seen or any(skip in cmd for skip in SKIP_PATTERNS):
                continue
            seen.add(cmd)

            try:
                if DRY_RUN:
                    discovered.append((cmd, "💤 (dry-run)"))
                    log(f"🧠 Would test: {cmd}", YELLOW)
                else:
                    r = scope.query(cmd).strip()
                    if r:
                        discovered.append((cmd, r))
                        log(f"🧠 Learned: {cmd} → {r}", GREEN)

                        if cmd not in known:
                            with open(COMMAND_FILE, "a") as f:
                                f.write(cmd + "\n")

                        if csv_file:
                            csv_writer.writerow([cmd, r])

                        if depth > 1 and r.isalpha() and len(r) < 12:
                            child_prefix = cmd.rstrip("?").split(":")
                            child_prefix.append(r.strip().upper())
                            for suffix2 in ["?", "VALue?", "STATe?", "RMS?"]:
                                deep = ":" + ":".join(child_prefix) + ":" + suffix2
                                deep = deep.replace("::", ":")
                                if deep in seen:
                                    continue
                                seen.add(deep)
                                try:
                                    deep_r = scope.query(deep).strip()
                                    if deep_r:
                                        discovered.append((deep, deep_r))
                                        log(f"🧬 Follow-up: {deep} → {deep_r}", GREEN)
                                        if csv_file:
                                            csv_writer.writerow([deep, deep_r])
                                        with open(COMMAND_FILE, "a") as f:
                                            f.write(deep + "\n")
                                except Exception:
                                    pass
            except Exception as e:
                err_text = str(e)
                color = RED
                if "TMO" in err_text:
                    color = "\033[95m"
                elif "Syntax" in err_text or "Undefined" in err_text:
                    color = "\033[96m"
                log(f"❌ {cmd:<40} → {err_text}", color)
                continue

            if not pinky_logged:
                log("🐰 Pinky connected the probe... again.", YELLOW)
                pinky_logged = True
            else:
                random_thinking()

    except KeyboardInterrupt:
        log("\n🛑 Focus probing interrupted by user (Ctrl+C)", RED)

    if csv_file:
        csv_file.close()
        log(f"📊 CSV results saved → {csv_name}", GREEN)

    if discovered:
        tag = idn.replace(',', '_').replace(' ', '_').replace('.', '_').strip() if idn else "unknown"
        timestamped = f"learned_focus_{tag}_{datetime.now():%Y%m%d_%H%M%S}.txt"
        latest = f"learned_focus_latest_{tag}.txt"
        with open(timestamped, "w") as f1, open(latest, "w") as f2:
            for cmd, result in discovered:
                f1.write(f"{cmd} → {result}\n")
                f2.write(f"{cmd} → {result}\n")
        log(f"💾 Focus-discovered {len(discovered)} commands → {timestamped}", GREEN)
        log(f"📌 Updated latest focus results → {latest}", YELLOW)
        log(f"✅ Total new commands discovered: {len(discovered)}", GREEN)
    else:
        log("🤷 No focus matches found.", YELLOW)

def save_log(name, results, idn=None):
    fname = f"doom_log_{name}_{datetime.now():%Y%m%d_%H%M%S}.txt"
    with open(fname, "w") as f:
        if idn:
            f.write(f"# Scope IDN: {idn}\n")
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

def setup_scpi_autocomplete(idn=None):
    cmds = load_all_commands(idn=idn)
    print(f"[DEBUG] Loaded {len(cmds)} SCPI commands for autocomplete")

    readline.set_completer_delims(" \t\n")  # Allow colons

    def completer(text, state):
        buffer = readline.get_line_buffer().strip()
        line = buffer.upper()

        # Match whole command if starting with ":" or partial otherwise
        if not line or line.startswith(":"):
            matches = [cmd for cmd in cmds if cmd.upper().startswith(line)]
        else:
            matches = [cmd for cmd in cmds if cmd.upper().startswith(":" + line)]

        if state == 0:
            print(f"\n[DEBUG] Autocomplete matches for '{buffer}':")
            for m in matches:
                print(" →", m)
        return matches[state] if state < len(matches) else None

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")

def main():
    if len(sys.argv) < 2:
        print("💀 DOOM SCPI Toolkit - Usage Guide 💀")
        print("====================================")
        print("  🔍 doom list                            List all VISA resources")
        print("  🧪 doom test      --ip <addr> | --usb   Run full SCPI test suite")
        print("  🎯 doom group     <GROUP> --ip | --usb  Test SCPI commands by group (e.g., MATH1)")
        print("  🧾 doom licenses  <ip>                  Query installed license keys")
        print("  📉 doom waveform  <CH> --ip | --usb     Retrieve waveform data (e.g., CHAN1)")
        print("  💣 doom fuzz      --ip <addr> | --usb   Fuzz scope with random SCPI queries")
        print("  🧠 doom learn     --ip <addr> [--prefix PREFIX] [--smart]")
        print("  🎯 doom focus     --ip <addr> --target PREFIX [--depth N] [--save-csv] [--wordlist FILE]")
        print("  ✉️ doom send \"<SCPI>\" --ip | --usb    Send any SCPI command (quoted)")
        print("  🐰 doom pinky                          Activate Gehirnwäsche mode (easter egg)")
        print("====================================")
        if DRY_RUN:
            print("🚫  NOTE: --dry-run mode is enabled — no SCPI commands will be sent!")
        print("🛠️  Example: doom test --ip 192.168.2.70")
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
        scope, idn = connect(resolve_scope(sys.argv))
        if scope:
            test_all(scope, idn=idn)
            scope.close()
    elif mode == "group":
        if len(sys.argv) < 3:
            log("❌ Group name required", RED)
            return
        scope, idn = connect(resolve_scope(sys.argv))
        if scope:
            test_group(scope, sys.argv[2], idn=idn)
            scope.close()
    elif mode == "waveform":
        scope, idn = connect(resolve_scope(sys.argv))
        if scope:
            run_waveform_test(scope, sys.argv[2] if len(sys.argv) > 2 else "CHAN1")
            scope.close()
    elif mode == "fuzz":
        scope, idn = connect(resolve_scope(sys.argv))
        if scope:
            fuzz_scope(scope, idn=idn)
            scope.close()
    elif mode == "learn":
        scope, idn = connect(resolve_scope(sys.argv))
        if scope:
            prefix = None
            if "--prefix" in sys.argv:
                idx = sys.argv.index("--prefix")
                if idx + 1 < len(sys.argv):
                    prefix = sys.argv[idx + 1].strip(":")
            prefix = None
            if "--prefix" in sys.argv:
                idx = sys.argv.index("--prefix")
                if idx + 1 < len(sys.argv):
                    prefix = sys.argv[idx + 1].strip(":")

            if "--smart" in sys.argv:
                smart_learn_scope(scope, idn=idn, prefix=prefix or "")
            else:
                learn_scope(scope, idn=idn, prefix=prefix)
            scope.close()
    elif mode == "focus":
        scope, idn = connect(resolve_scope(sys.argv))
        if scope:
            prefix = ":POWer:QUALity:"
            if "--target" in sys.argv:
                idx = sys.argv.index("--target")
                if idx + 1 < len(sys.argv):
                    target = sys.argv[idx + 1].upper()
                    if target == "POWER_QUALITY":
                        prefix = ":POWer:QUALity:"
                    else:
                        prefix = ":" + target.replace("_", ":").upper() + ":"
            focus_probe(scope, idn=idn, prefix=prefix)
            scope.close()

    elif mode == "pinky":
        from pinky_quotes import phrases
        colors = [GREEN, YELLOW, RED, "\033[95m", "\033[96m", "\033[94m", "\033[90m"]  # magenta, cyan, blue, gray
        log("🐰 Initiating Gehirnwäsche protocol with Pinky & Brain quotes...\n", YELLOW)
        try:
            while True:
                time.sleep(random.uniform(0.3, 1.2))
                quote = random.choice(phrases)
                color = random.choice(colors)
                log(quote, color)
        except KeyboardInterrupt:
            log("\n🧠 Brain override: Gehirnwäsche interrupted by user (Ctrl+C)", RED)
    elif mode == "send":
        # Collect everything after "send"
        args = sys.argv[2:]

        # Detect connection target
        if "--ip" in args:
            idx = args.index("--ip")
            if idx + 1 < len(args):
                resource = f"TCPIP0::{args[idx + 1]}::INSTR"
            else:
                log("❌ Missing IP after --ip", RED)
                return
        elif "--usb" in args:
            resource = find_usb()
        else:
            log("❌ Specify --ip <addr> or --usb", RED)
            return

        # Remove known flags to isolate SCPI command
        stripped_args = [a for a in args if a not in ["--ip", "--usb"] and not re.match(r"\d+\.\d+\.\d+\.\d+", a)]
        cmd = " ".join(stripped_args).strip()

        # Interactive console if no command is passed
        if not cmd:
            scope, idn = connect(resource)
            if not scope:
                return
            log("💡 Enter SCPI command interactively (TAB autocompletion enabled)", YELLOW)
            setup_scpi_autocomplete(idn=idn)
            while True:
                try:
                    cmd = input("🧠 SCPI> ").strip()
                    if not cmd:
                        continue
                    if cmd.lower() in ["exit", "quit"]:
                        log("👋 Exiting SCPI console.", YELLOW)
                        break
                    if "?" in cmd:
                        response = scope.query(cmd).strip()
                        log(f"✅ Response: {response}" if response else "⚠️  Empty response", GREEN)
                    else:
                        scope.write(cmd)
                        log("✅ Command sent (no response expected)", GREEN)
                except KeyboardInterrupt:
                    log("\n🛑 Aborted.", RED)
                    break
                except Exception as e:
                    log(f"❌ SCPI Error: {e}", RED)
            scope.close()
            return

        # If command was passed as argument, send it once and exit
        scope, idn = connect(resource)
        if scope:
            log(f"🚀 Sending SCPI command: {cmd}", YELLOW)
            try:
                if "?" in cmd:
                    response = scope.query(cmd).strip()
                    log(f"✅ Response: {response}" if response else "⚠️  Empty response", GREEN)
                else:
                    scope.write(cmd)
                    log("✅ Command sent (no response expected)", GREEN)
            except Exception as e:
                log(f"❌ SCPI Error: {e}", RED)
            finally:
                scope.close()
    else:
        log("❌ Unknown command", RED)

if __name__ == "__main__":
    main()
