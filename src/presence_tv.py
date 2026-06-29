#!/usr/bin/env python3
"""Détecteur de présence (LD2450 mmWave) → switch input TV Samsung via IR.

Présence détectée  → HDMI 1
Absence > timeout   → HDMI 2

Décodage LD2450 : coordonnées encodées en signe+magnitude (bit 15 = signe),
PAS en complément à deux. Voir _decode_coord().
"""

import configparser
import logging
import os
import signal
import struct
import subprocess
import sys
import time

import serial

CONFIG_PATH = os.environ.get(
    "PRESENCE_TV_CONFIG",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "presence_tv.ini"),
)


def load_config(path):
    cfg = configparser.ConfigParser()
    if not cfg.read(path):
        raise FileNotFoundError(f"Config introuvable : {path}")
    return cfg


def _decode_coord(raw):
    """LD2450 : signe+magnitude. bit15 set -> positif, clear -> négatif."""
    magnitude = raw & 0x7FFF
    return magnitude if (raw & 0x8000) else -magnitude


class LD2450:
    """Lecteur de trames LD2450 avec resynchronisation sur le stream UART."""

    HEADER = bytes([0xAA, 0xFF, 0x03, 0x00])
    FOOTER = bytes([0x55, 0xCC])
    FRAME_LEN = 30          # header(4) + 3 cibles x 8 + footer(2)
    MAX_TARGETS = 3
    _MAX_BUF = 256          # garde-fou anti-croissance buffer

    def __init__(self, port, baud, timeout=0.1):
        self.ser = serial.Serial(port, baud, timeout=timeout)
        self._buf = bytearray()

    def close(self):
        if self.ser.is_open:
            self.ser.close()

    def _parse_targets(self, frame):
        targets = []
        for i in range(self.MAX_TARGETS):
            offset = 4 + i * 8
            rx, ry, rspeed, res = struct.unpack_from("<HHHH", frame, offset)
            if res > 0:  # résolution non nulle = cible valide
                targets.append(
                    {
                        "x": _decode_coord(rx),
                        "y": _decode_coord(ry),
                        "speed": _decode_coord(rspeed),
                        "res": res,
                    }
                )
        return targets

    def read_frame(self):
        """Retourne la liste des cibles d'une trame complète, ou None."""
        try:
            chunk = self.ser.read(self.FRAME_LEN)
        except serial.SerialException:
            # readiness race PL011 : lecture transitoire vide, resync au prochain tour
            return None
        if chunk:
            self._buf.extend(chunk)

        idx = self._buf.find(self.HEADER)
        if idx == -1:
            # pas de header : ne garder que la fin (header potentiel à cheval)
            if len(self._buf) > self._MAX_BUF:
                del self._buf[:-len(self.HEADER)]
            return None

        if idx > 0:
            del self._buf[:idx]  # jeter les octets avant le header

        if len(self._buf) < self.FRAME_LEN:
            return None

        frame = bytes(self._buf[: self.FRAME_LEN])
        if frame[-2:] != self.FOOTER:
            # footer absent : trame corrompue, avancer d'un octet et resync
            del self._buf[:1]
            return None

        del self._buf[: self.FRAME_LEN]
        return self._parse_targets(frame)


class IRController:
    def __init__(self, device, file_hdmi1, file_hdmi2, repeat=2, repeat_gap=0.1):
        self.device = device
        self.files = {1: file_hdmi1, 2: file_hdmi2}
        self.repeat = repeat
        self.repeat_gap = repeat_gap

    def _send_once(self, path):
        result = subprocess.run(
            ["ir-ctl", "-d", self.device, f"--send={path}"],
            capture_output=True,
        )
        if result.returncode != 0:
            logging.error("IR erreur : %s", result.stderr.decode().strip())
            return False
        return True

    def switch_input(self, hdmi):
        path = self.files[hdmi]
        logging.info("Switch TV -> HDMI %d", hdmi)
        for n in range(self.repeat):
            self._send_once(path)
            if n < self.repeat - 1:
                time.sleep(self.repeat_gap)


def in_zone(target, zone):
    if zone is None:
        return True
    return (
        zone["x_min"] <= target["x"] <= zone["x_max"]
        and zone["y_min"] <= target["y"] <= zone["y_max"]
    )


def build_zone(cfg):
    if not cfg.getboolean("zone", "enabled", fallback=False):
        return None
    return {
        "x_min": cfg.getint("zone", "x_min"),
        "x_max": cfg.getint("zone", "x_max"),
        "y_min": cfg.getint("zone", "y_min"),
        "y_max": cfg.getint("zone", "y_max"),
    }


class Runner:
    def __init__(self):
        self._running = True

    def stop(self, *_):
        logging.info("Arrêt demandé.")
        self._running = False

    @property
    def running(self):
        return self._running


def main():
    cfg = load_config(CONFIG_PATH)

    logging.basicConfig(
        level=cfg.get("logging", "level", fallback="INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    port = cfg.get("serial", "port")
    baud = cfg.getint("serial", "baud")
    timeout_s = cfg.getfloat("presence", "timeout_s")
    poll_s = cfg.getfloat("presence", "poll_s", fallback=0.033)

    zone = build_zone(cfg)

    ir = IRController(
        device=cfg.get("ir", "device"),
        file_hdmi1=cfg.get("ir", "file_hdmi1"),
        file_hdmi2=cfg.get("ir", "file_hdmi2"),
        repeat=cfg.getint("ir", "repeat", fallback=2),
        repeat_gap=cfg.getfloat("ir", "repeat_gap_s", fallback=0.1),
    )

    runner = Runner()
    signal.signal(signal.SIGTERM, runner.stop)
    signal.signal(signal.SIGINT, runner.stop)

    sensor = LD2450(port, baud)
    logging.info("Démarrage détecteur présence — port=%s baud=%d", port, baud)

    current_input = None
    last_presence = time.monotonic()

    try:
        while runner.running:
            targets = sensor.read_frame()
            if targets is None:
                time.sleep(0.005)
                continue

            present = any(in_zone(t, zone) for t in targets)
            now = time.monotonic()

            if present:
                last_presence = now
                if current_input != 1:
                    ir.switch_input(1)
                    current_input = 1
            elif current_input != 2 and (now - last_presence) > timeout_s:
                ir.switch_input(2)
                current_input = 2

            time.sleep(poll_s)
    finally:
        sensor.close()
        logging.info("Capteur fermé. Sortie.")


if __name__ == "__main__":
    sys.exit(main())
