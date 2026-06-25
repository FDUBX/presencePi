#!/usr/bin/env python3
"""Moniteur live LD2450 — affiche les cibles décodées (x, y, vitesse, res).

Usage de réglage (calibration zone) AVANT mise en prod :
    python3 tools/ld2450_monitor.py --port /dev/ttyAMA0 --baud 256000

Ctrl+C pour quitter. Bouger dans la pièce, noter les x/y aux limites voulues
puis reporter dans [zone] de config/presence_tv.ini.
"""

import argparse
import os
import sys
import time

# Réutilise la classe LD2450 du service (pas de duplication du décodage)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from presence_tv import LD2450  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="Moniteur live LD2450.")
    p.add_argument("--port", default="/dev/ttyAMA0")
    p.add_argument("--baud", type=int, default=256000)
    args = p.parse_args()

    sensor = LD2450(args.port, args.baud)
    print(f"Lecture {args.port} @ {args.baud} — Ctrl+C pour quitter.\n")
    try:
        while True:
            targets = sensor.read_frame()
            if targets is None:
                time.sleep(0.005)
                continue
            if not targets:
                print("\r(aucune cible)                                        ", end="")
            else:
                line = " | ".join(
                    f"T{i}: x={t['x']:+5d} y={t['y']:+5d} v={t['speed']:+4d} res={t['res']}"
                    for i, t in enumerate(targets)
                )
                print("\r" + line + "    ", end="")
            sys.stdout.flush()
    except KeyboardInterrupt:
        print("\nArrêt.")
    finally:
        sensor.close()


if __name__ == "__main__":
    main()
