# 💀 DOOM3 SCPI Toolkit for Rigol MSO5000 Series

This is a brutal, fully-featured SCPI interrogation and fuzzing toolkit for Rigol MSO5000 oscilloscopes — with smart command discovery, waveform capture, and interactive autocompletion.

---

## ⚡ Features

- 🔍 List all connected VISA instruments
- 🧪 Run full SCPI test suites on the scope
- 🎯 Test SCPI command groups (e.g., `MATH1`, `CHANnel1`, etc.)
- 💣 Fuzz the scope with randomized SCPI input
- 🧠 Discover undocumented SCPI commands (learn mode)
- ✉️ Send arbitrary SCPI commands via CLI or interactive shell
- 🧾 Query Rigol license key status via HTTP
- 📉 Retrieve waveform data over USB or LAN
- 🤖 Interactive SCPI shell with fuzzy autocompletion (TAB support!)
- 📁 Logs results with timestamp AND scope ID to keep different devices separate
- 🧬 Learns and stores SCPI capabilities **per device**, avoiding cross-contamination

---

## 🚀 Usage

### List Devices
```bash
doom3 list
```

### Run full test
```bash
doom3 test --ip 192.168.2.70
```

### Run a specific group
```bash
doom3 group MATH1 --ip 192.168.2.70
```

### Query licenses
```bash
doom3 licenses 192.168.2.70
```

### Get waveform
```bash
doom3 waveform CHAN1 --ip 192.168.2.70
```

### Learn new SCPI commands
```bash
doom3 learn --ip 192.168.2.70
```

### Fuzz the hell out of it
```bash
doom3 fuzz --ip 192.168.2.70
```

### Send a command directly
```bash
doom3 send ":CHANnel1:SCALe?" --ip 192.168.2.70
```

### Or use interactive mode with autocompletion:
```bash
doom3 send --ip 192.168.2.70
```
Then type and press `TAB`:
```
🧠 SCPI> :CHANnel1:SCALe?
```

---

## 📂 Logs & Learning

- All logs are saved to `doom3_log_*` with timestamps.
- Learned SCPI commands are saved **per device**, using the scope’s ID.
  Example:
  ```
  learned_scpi_latest_RIGOL_TECHNOLOGIES_MSO5074_MS5A223604686.txt
  ```

---

## 🛠 Requirements

- Python 3.6+
- `pyvisa`, `readline`, `requests`
- VISA backend (NI-VISA or pyvisa-py)
- Rigol MSO5000-series oscilloscope (USB or LAN)

---

## ⚠️ Warnings

- Fuzzing and learn modes can push the scope into unstable states.
- Always test with caution and log your results.
- Mixing learned SCPI commands from multiple scopes is now prevented (by design).

---

## ☠️ Credits

- Inspired by Pinky & the Brain
- BFG9000 included
