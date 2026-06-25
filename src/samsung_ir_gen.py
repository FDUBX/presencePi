#!/usr/bin/env python3
"""Génère un fichier raw ir-ctl (pulse/space) pour un code Samsung 32 bits.

Protocole Samsung (≈ NEC mais leader 4500/4500) :
  leader : pulse 4500, space 4500
  bit 0  : pulse 560,  space 560
  bit 1  : pulse 560,  space 1690
  trailer: pulse 560,  space <gap>

ATTENTION : l'ordre des bits (MSB-first vs LSB-first) varie selon la source du
code hex. Par défaut MSB-first. Si la TV ne réagit pas, réessayer avec --lsb.
Toujours valider l'émission avec la caméra du smartphone (LED violette).

Usage :
  python3 samsung_ir_gen.py 0xE0E09768 > ir/hdmi1.txt
  python3 samsung_ir_gen.py --lsb 0xE0E09768 > ir/hdmi1.txt
"""

import argparse

LEADER = (4500, 4500)
PULSE = 560
SPACE_0 = 560
SPACE_1 = 1690
GAP = 47000


def gen(code, bits=32, lsb_first=False):
    lines = ["# Samsung 32-bit IR (généré par samsung_ir_gen.py)", f"# code=0x{code:08X} lsb_first={lsb_first}"]
    lines.append(f"pulse {LEADER[0]}")
    lines.append(f"space {LEADER[1]}")

    order = range(bits) if lsb_first else range(bits - 1, -1, -1)
    for i in order:
        bit = (code >> i) & 1
        lines.append(f"pulse {PULSE}")
        lines.append(f"space {SPACE_1 if bit else SPACE_0}")

    lines.append(f"pulse {PULSE}")
    lines.append(f"space {GAP}")
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description="Génère un raw ir-ctl Samsung 32 bits.")
    p.add_argument("code", help="code hex 32 bits, ex: 0xE0E09768")
    p.add_argument("--lsb", action="store_true", help="émettre LSB-first au lieu de MSB-first")
    p.add_argument("--bits", type=int, default=32)
    args = p.parse_args()

    code = int(args.code, 16)
    print(gen(code, bits=args.bits, lsb_first=args.lsb), end="")


if __name__ == "__main__":
    main()
