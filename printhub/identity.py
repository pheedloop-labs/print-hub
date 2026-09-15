"""Stable identity for this hub and its printers, and how to reach it.

The OnSite app addresses a hub and a printer by id, not by name. Names are
for humans and they change: a queue gets renamed, two venues both have a
"Zebra", and the Windows queue name is an implementation detail the app
should not have to care about.

**Ids are assigned once and persisted.** `identity.json` is machine-local and
gitignored, like the DEVMODE blobs. Losing it re-issues every id and breaks
whatever the app had paired to, so it is written on first sight and never
rewritten afterwards.

Printer ids are keyed by Windows queue name, which is the most stable handle
available. That survives the case in Verified 56, where removing and
re-adding a printer brought it back with the same name and port. It does not
survive a rename, which re-issues the id; there is nothing better to key on,
since the driver exposes no durable serial.

**Link-local addresses are excluded from what the app is told.** This box has
two interfaces and `getaddrinfo` reports both: Wi-Fi on 192.168.1.30 and
Ethernet on a 169.254 address with no DHCP behind it. Handing the app the
169.254 one would look correct and never connect.
"""

import json
import pathlib
import secrets
import socket
import threading

CONFIG_NAME = "identity.json"
HUB_PREFIX = "hub_"
PRINTER_PREFIX = "prn_"
ID_BYTES = 6          # 12 hex chars: short enough for a QR, ample for a venue


def _new_id(prefix):
    return prefix + secrets.token_hex(ID_BYTES)


def is_link_local(ip):
    return ip.startswith("169.254.")


def is_loopback(ip):
    return ip.startswith("127.")


def primary_address():
    """The address this box would use to reach the network, or None.

    Opens a UDP socket and asks the routing table where it would send; no
    packet is sent and nothing has to be reachable. This is the address the
    app should be given, and on this bench it correctly picks the Wi-Fi
    address over the link-local Ethernet one.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def addresses():
    """Every usable IPv4 address, primary first. Link-local is left out."""
    found = []
    try:
        for _, _, _, _, sa in socket.getaddrinfo(socket.gethostname(), None,
                                                 socket.AF_INET):
            ip = sa[0]
            if ip not in found and not is_loopback(ip) and not is_link_local(ip):
                found.append(ip)
    except socket.gaierror:
        pass

    primary = primary_address()
    if primary and not is_link_local(primary):
        if primary in found:
            found.remove(primary)
        found.insert(0, primary)
    return found


class Identity:
    """Reads identity.json, assigning ids as printers are first seen."""

    def __init__(self, hub_dir):
        self.path = pathlib.Path(hub_dir) / CONFIG_NAME
        self._lock = threading.Lock()
        self._data = {"hub_id": None, "printers": {}}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data.get("printers"), dict):
                    self._data = {
                        "hub_id": data.get("hub_id"),
                        "printers": data["printers"],
                    }
            except (OSError, ValueError):
                # A corrupt identity file would otherwise re-issue every id
                # silently. Keep the in-memory defaults and let _save rewrite
                # it, but say so where a human will see it.
                self._data = {"hub_id": None, "printers": {}}
        if not self._data["hub_id"]:
            self._data["hub_id"] = _new_id(HUB_PREFIX)
            self._save()

    def _save(self):
        try:
            self.path.write_text(
                json.dumps(self._data, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass

    @property
    def hub_id(self):
        return self._data["hub_id"]

    def printer_id(self, queue):
        """This queue's id, assigning one the first time it is seen."""
        with self._lock:
            existing = self._data["printers"].get(queue)
            if existing:
                return existing
            new = _new_id(PRINTER_PREFIX)
            self._data["printers"][queue] = new
            self._save()
            return new

    def queue_for(self, printer_id):
        """Reverse lookup. None when the id is unknown to this hub."""
        for queue, pid in self._data["printers"].items():
            if pid == printer_id:
                return queue
        return None
