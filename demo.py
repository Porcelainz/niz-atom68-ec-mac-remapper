"""Simulated NIZ 68EC for `./niz68 gui --demo` — speaks the same HID protocol."""
import glob
import json
import os
import types

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_L1 = [1, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 14,
              28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 84,
              42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 83,
              55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 87, 86,
              67, 68, 69, 70, 71, 156, 74, 88, 89, 90]


def _pkt(l, k, codes):
    b = bytearray(64)
    b[1], b[2], b[3], b[4], b[5] = 0xF0, l, k, 0, len(codes)
    b[6:6 + len(codes)] = bytes(codes)
    return bytes(b)


def _initial_slots():
    real = sorted(glob.glob(os.path.join(HERE, "backups", "keymap-*.json")))
    if real:
        with open(real[0]) as f:
            data = json.load(f)
        out = {}
        for lk, pk in data["slots"].items():
            l, k = (int(x) for x in lk.split(":"))
            out[(l, k)] = [bytes.fromhex(p) for p in pk]
        return out, data.get("version") or "68EC(S)BLe;DEMO;"
    out = {}
    for l in range(1, 10):
        for k in range(1, 69):
            out[(l, k)] = [_pkt(l, k, [DEFAULT_L1[k - 1]] if l % 3 == 1 else [])]
    return out, "68EC(S)BLe;DEMO;"


class FakeKB:
    def __init__(self):
        self.slots, self.ver = _initial_slots()
        self.out, self.writing = [], None

    def open_path(self, p):
        self.out = []

    def close(self):
        pass

    def write(self, data):
        p = bytes(data[1:])
        if self.writing is not None:
            if p[1] == 0xF6 and all(x == 0xF6 for x in p[1:]):
                new, i, pk = {}, 0, self.writing
                while i < len(pk):
                    h = pk[i]
                    packs = [h]
                    i += 1
                    if h[4] in (2, 3, 4):
                        ln = (h[9] << 8) | h[10]
                        extra = max(0, (ln + 52) // 53 - 1)
                        packs += pk[i:i + extra]
                        i += extra
                    new[(h[2], h[3])] = packs
                self.slots, self.writing = new, None
            else:
                self.writing.append(p)
            return 65
        cmd = p[1]
        if cmd == 0xF9:
            self.out.append(b"\x00\xf9" + self.ver.encode().ljust(62, b"\0")[:62])
        elif cmd == 0xF2:
            for key in sorted(self.slots):
                self.out += self.slots[key]
            self.out.append(bytes([0xF6] * 64))
        elif cmd == 0xF1:
            self.writing = []
        elif cmd == 0xE3:
            vals = b"".join(((i * 37) % 900).to_bytes(4, "little") for i in range(68))
            for off in range(0, len(vals), 60):
                ch = vals[off:off + 60]
                self.out.append(bytes([0, 0xE3, len(ch)]) + ch + bytes(61 - len(ch)))
            self.out.append(bytes([0, 0xE6]) + bytes(62))
        return 65

    def read(self, n, timeout=0):
        return list(self.out.pop(0)) if self.out else []


def make_fake_hid():
    kb = FakeKB()
    return types.SimpleNamespace(
        enumerate=lambda: [{"vendor_id": 0x0483, "product_id": 0x5132, "interface_number": 1,
                            "usage_page": 0x8C, "usage": 1, "path": b"demo",
                            "product_string": "68EC-S (demo)"}],
        device=lambda: kb)
