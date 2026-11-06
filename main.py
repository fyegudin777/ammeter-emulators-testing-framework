import sys
import threading
import time

# Some emulators print non-ASCII characters (e.g. Greenlee's "Ω" for Ohms).
# On Windows the console's default codepage (cp1252) can't encode those,
# which previously crashed the emulator thread on its first request. Forcing
# UTF-8 stdout here fixes it for every entry point that imports main.py's
# logic, without changing the emulators' debug-print text. See README.md
# "Bugs Fixed" section.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from Ammeters.Circutor_Ammeter import CircutorAmmeter
from Ammeters.Entes_Ammeter import EntesAmmeter
from Ammeters.Greenlee_Ammeter import GreenleeAmmeter
from Ammeters.client import request_current_from_ammeter

# Ports and commands must match README.md and each ammeter's `get_current_command`
# property exactly (the server does a byte-for-byte comparison in base_ammeter.py).
GREENLEE_PORT = 5000
ENTES_PORT = 5001
CIRCUTOR_PORT = 5002


def run_greenlee_emulator():
    greenlee = GreenleeAmmeter(GREENLEE_PORT)
    greenlee.start_server()

def run_entes_emulator():
    entes = EntesAmmeter(ENTES_PORT)
    entes.start_server()

def run_circutor_emulator():
    circutor = CircutorAmmeter(CIRCUTOR_PORT)
    circutor.start_server()

if __name__ == "__main__":
    # Start each ammeter in a separate thread
    threading.Thread(target=run_greenlee_emulator, daemon=True).start()
    threading.Thread(target=run_entes_emulator, daemon=True).start()
    threading.Thread(target=run_circutor_emulator, daemon=True).start()

    # Bug fix (see README.md "Bugs Fixed" section):
    # 1. Ports here didn't match the ports documented in README.md/used by the
    #    framework (5001/5002/5003 vs 5000/5001/5002) - now aligned.
    # 2. The commands sent only contained the prefix (e.g. b'MEASURE_GREENLEE')
    #    while base_ammeter.py compares the *exact* bytes against
    #    get_current_command (e.g. b'MEASURE_GREENLEE -get_measurement'), so the
    #    request would never match and no data was ever returned. Sending the
    #    full command fixes this.

    # Wait for the servers to start, if you have problem restarting the servers between runs try increasing sleep time.
    time.sleep(5)
    request_current_from_ammeter(GREENLEE_PORT, b'MEASURE_GREENLEE -get_measurement')
    request_current_from_ammeter(ENTES_PORT, b'MEASURE_ENTES -get_data')
    request_current_from_ammeter(CIRCUTOR_PORT, b'MEASURE_CIRCUTOR -get_measurement -current')
