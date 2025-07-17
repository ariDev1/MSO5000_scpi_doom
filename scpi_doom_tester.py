import sys
import time
import pyvisa
from datetime import datetime

COMMAND_FILE = "scpi_command_list.txt"
SKIP_PATTERNS = ["WAV:DATA?", "DISPlay:DATA?"]

# ANSI colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

def load_commands():
    with open(COMMAND_FILE, "r") as f:
        return [line.strip() for line in f if line.strip() and not any(skip in line for skip in SKIP_PATTERNS)]

def log_cli(idx, total, cmd, result):
    if result.startswith("✅"):
        color = GREEN
    elif result.startswith("⚠️"):
        color = YELLOW
    elif result.startswith("❌"):
        color = RED
    else:
        color = RESET
    print(f"{color}▶ [{idx}/{total}] {cmd:<40} → {result}{RESET}")

def test_scope(resource_str, commands):
    rm = pyvisa.ResourceManager()
    try:
        print(f"🔌 Connecting to {resource_str} ...")
        scope = rm.open_resource(resource_str)
        scope.timeout = 3000
        scope.chunk_size = 102400
        idn = scope.query("*IDN?")
        print(f"✅ Connected: {idn}\n")
    except Exception as e:
        print(f"{RED}❌ Connection failed: {e}{RESET}")
        return

    results = []
    print("📡 Running SCPI command test...\n")
    total = len(commands)
    for i, cmd in enumerate(commands, 1):
        try:
            resp = scope.query(cmd).strip()
            if resp:
                result = f"✅ {resp}"
            else:
                result = "⚠️ Empty response"
        except Exception as e:
            result = f"❌ {e}"
        results.append((cmd, result))
        log_cli(i, total, cmd, result)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logfile = f"scpi_doom_log_{ts}.txt"
    with open(logfile, "w") as f:
        for cmd, result in results:
            f.write(f"{cmd:<40} → {result}\n")
    print(f"\n💾 Log saved to {logfile}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 scpi_doom_tester.py <IP>  or  python3 scpi_doom_tester.py usb")
        sys.exit(1)

    target = sys.argv[1].strip().lower()
    if target == "usb":
        rm = pyvisa.ResourceManager()
        usb_list = [r for r in rm.list_resources() if "USB" in r]
        if not usb_list:
            print(f"{RED}❌ No USB VISA device found.{RESET}")
            sys.exit(1)
        resource_str = usb_list[0]
    else:
        resource_str = f"TCPIP0::{target}::INSTR"

    cmds = load_commands()
    test_scope(resource_str, cmds)
