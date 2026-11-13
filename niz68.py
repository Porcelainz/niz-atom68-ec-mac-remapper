#!/usr/bin/env python3
"""
niz68 — macOS command-line keymap tool for NIZ 5th-gen 68EC keyboards.

Protocol reverse-engineered from the official Windows programming software
(68ECHWI.dll, V1.3.1). Only the keymap / counter / version commands are
implemented. The firmware-update path is deliberately NOT implemented.

Wire format: HID output report, report ID 0, 64 data bytes.
    request : [0]=0x00 [1]=cmd [2..63]=payload
    key slot: [0]=0x00 [1]=0xF0 [2]=layer(1..9) [3]=key(1..68) [4]=type ...
      type 0 (normal) : [5]=n [6..6+n)=key codes (n>1 = key combo)
      type 1 (repeat) : [5..6]=param(BE) [7]=n [8..8+n)=key codes
      type 2/3/4      : [9..10]=length(BE); payload continues in extra
                         64-byte packets when length > 53
"""
import argparse
import datetime as _dt
import json
import os
import sys
import time

try:
    import hid  # pip install hidapi
except ImportError:  # pragma: no cover
    hid = None

VID_WIN = 0x0483
PIDS_WIN = (0x5032, 0x5132, 0x5232, 0x5332)
CONFIG_INTERFACE = 1
VID_MAC_MODE = 0x05AC
PIDS_MAC_MODE = (0x0220, 0x022C, 0x0252)

CMD_READ_COUNTER = 0xE3
CMD_COUNTER_DATA = 0xE3
CMD_COUNTER_END = 0xE6
CMD_KEY_DATA = 0xF0
CMD_WRITE_ALL = 0xF1
CMD_READ_ALL = 0xF2
CMD_DATA_END = 0xF6
CMD_VERSION = 0xF9

LAYERS = 9          # slots the official software iterates over
KEYS_PER_LAYER = 68
PKT = 64
MACRO_HEADER = 11   # bytes of header in a type-2/3/4 first packet
MACRO_CHUNK = PKT - MACRO_HEADER  # 53

LAYER_NAMES = {1: "NoneFn", 2: "RightFn", 3: "LeftFn"}
TYPE_NAMES = {0: "normal", 1: "repeat", 2: "macro", 3: "macro3", 4: "macro4"}

# Key codes used by NIZ 5th-gen firmware (same table as the 66EC; verified
# against the 68EC by reading the default layer of a real board).
CODES = {
    0: "", 1: "ESC", 2: "F1", 3: "F2", 4: "F3", 5: "F4", 6: "F5", 7: "F6",
    8: "F7", 9: "F8", 10: "F9", 11: "F10", 12: "F11", 13: "F12", 14: "`",
    15: "1", 16: "2", 17: "3", 18: "4", 19: "5", 20: "6", 21: "7", 22: "8",
    23: "9", 24: "0", 25: "-", 26: "=", 27: "Backspace", 28: "Tab", 29: "Q",
    30: "W", 31: "E", 32: "R", 33: "T", 34: "Y", 35: "U", 36: "I", 37: "O",
    38: "P", 39: "[", 40: "]", 41: "\\", 42: "CapsLock", 43: "A", 44: "S",
    45: "D", 46: "F", 47: "G", 48: "H", 49: "J", 50: "K", 51: "L", 52: ";",
    53: "'", 54: "Enter", 55: "LShift", 56: "Z", 57: "X", 58: "C", 59: "V",
    60: "B", 61: "N", 62: "M", 63: ",", 64: ".", 65: "/", 66: "RShift",
    67: "LCtrl", 68: "LWin", 69: "LAlt", 70: "Space", 71: "RAlt", 72: "RWin",
    73: "Menu", 74: "RCtrl", 75: "Wakeup", 76: "Sleep", 77: "Power",
    78: "PrtSc", 79: "ScrollLock", 80: "Pause", 81: "Insert", 82: "Home",
    83: "PageUp", 84: "Delete", 85: "End", 86: "PageDown", 87: "Up",
    88: "Left", 89: "Down", 90: "Right", 91: "NumLock", 92: "KP/",
    93: "KP*", 94: "KP7", 95: "KP8", 96: "KP9", 97: "KP4", 98: "KP5",
    99: "KP6", 100: "KP1", 101: "KP2", 102: "KP3", 103: "KP0", 104: "KP.",
    105: "KP-", 106: "KP+", 107: "KPEnter", 108: "NextTrack",
    109: "PrevTrack", 110: "StopMedia", 111: "PlayPause", 112: "Mute",
    113: "VolUp", 114: "VolDown", 115: "MediaSelect", 116: "Email",
    117: "Calculator", 118: "MyComputer", 119: "WWWSearch", 120: "WWWHome",
    121: "WWWBack", 122: "WWWForward", 123: "WWWStop", 124: "WWWRefresh",
    125: "WWWFavorites", 126: "MouseLeft", 127: "MouseRight",
    128: "MouseUp", 129: "MouseDown", 130: "MouseBtnLeft",
    131: "MouseBtnRight", 132: "MouseBtnMiddle", 133: "WheelUp",
    134: "WheelDown", 135: "BacklightSwitch", 136: "BacklightMacro",
    137: "Demonstrate", 138: "StarShower", 139: "Riffle", 140: "DemoStop",
    141: "Breathe", 142: "BreatheSeq-", 143: "BreatheSeq+",
    144: "Backlight-", 145: "Backlight+", 146: "Aurora",
    147: "ColorBreathe", 148: "BackColorExchange", 149: "TriggerPoint",
    150: "KeyboardLock", 151: "Shift&Up", 152: "Ctrl/CapsSwap",
    153: "WinLock", 154: "MouseLock", 155: "Win/MacSwitch", 156: "RFn",
    157: "MouseUnitPixel", 158: "MouseUnitTime", 159: "ProgrammableKbd",
    160: "BacklightRec1", 161: "BacklightRec2", 162: "BacklightRec3",
    163: "BacklightRec4", 164: "BacklightRec5", 165: "BacklightRec6",
    166: "LFn", 167: "Wire/Wireless", 168: "BTD1", 169: "BTD2",
    170: "BTD3", 171: "Game", 172: "ECO", 173: "MouseFirstDelay",
    174: "KeyRepeatRate", 175: "KeyResponseDelay", 176: "USBReportRate",
    177: "KeyScanPeriod", 199: "MouseDoubleClick", 204: "<>|",
}
NAME_TO_CODE = {v.lower(): k for k, v in CODES.items() if v}


def code_name(c):
    return CODES.get(c, f"#{c}")


def parse_code(s):
    s = s.strip()
    if s.isdigit():
        v = int(s)
    elif s.lower().startswith("0x"):
        v = int(s, 16)
    elif s.lower() in NAME_TO_CODE:
        v = NAME_TO_CODE[s.lower()]
    else:
        raise SystemExit(f"不認得的按鍵名稱: {s!r}（用 `niz68 codes` 查清單，或直接給數字）")
    if not 0 <= v <= 255:
        raise SystemExit(f"按鍵代碼超出範圍 0-255: {v}")
    return v


# --------------------------------------------------------------------------
# Slot model
# --------------------------------------------------------------------------
class Slot:
    """One (layer, key) entry as raw 64-byte packets."""

    def __init__(self, packets):
        self.packets = [bytes(p) for p in packets]

    @property
    def head(self):
        return self.packets[0]

    @property
    def layer(self):
        return self.head[2]

    @property
    def key(self):
        return self.head[3]

    @property
    def type(self):
        return self.head[4]

    def normal_codes(self):
        h = self.head
        n = h[5]
        return list(h[6:6 + n])

    def describe(self):
        t = self.type
        if t == 0:
            return "+".join(code_name(c) for c in self.normal_codes())
        if t == 1:
            n = self.head[7]
            return "[連發] " + "+".join(code_name(c) for c in self.head[8:8 + n])
        return f"[{TYPE_NAMES.get(t, f'type{t}')}]"

    def to_json(self):
        return [p.hex() for p in self.packets]

    @classmethod
    def from_json(cls, data):
        return cls([bytes.fromhex(p) for p in data])

    @staticmethod
    def normal(layer, key, codes):
        """Same encoding as the official software's normal-key writer."""
        codes = [c for c in codes if c]
        buf = bytearray(PKT)
        buf[1] = CMD_KEY_DATA
        buf[2] = layer
        buf[3] = key
        buf[4] = 0
        buf[5] = len(codes)
        buf[6:6 + len(codes)] = bytes(codes)
        return Slot([bytes(buf)])


def empty_slot_packet(layer, key):
    buf = bytearray(PKT)
    buf[1] = CMD_KEY_DATA
    buf[2] = layer
    buf[3] = key
    return bytes(buf)


# --------------------------------------------------------------------------
# Device
# --------------------------------------------------------------------------
class DeviceError(Exception):
    pass


def find_devices():
    if hid is None:
        raise DeviceError("缺少 hidapi 套件，請先執行 ./setup.sh")
    cfg, macmode = [], []
    for d in hid.enumerate():
        vid, pid = d["vendor_id"], d["product_id"]
        if vid == VID_WIN and pid in PIDS_WIN:
            cfg.append(d)
        elif vid == VID_MAC_MODE and pid in PIDS_MAC_MODE and "NIZ" in (d.get("product_string") or "").upper():
            macmode.append(d)
    return cfg, macmode


def pick_config_interface(cands):
    by_if = [d for d in cands if d.get("interface_number") == CONFIG_INTERFACE]
    if by_if:
        return by_if[0]
    vendor = [d for d in cands if d.get("usage_page", 0) >= 0xFF00]
    if vendor:
        return vendor[0]
    return None


class NiZ:
    def __init__(self, verbose=False):
        self.dev = None
        self.verbose = verbose

    def open(self):
        cfg, macmode = find_devices()
        d = pick_config_interface(cfg)
        if d is None:
            if macmode:
                raise DeviceError(
                    "找到 NIZ 鍵盤，但它在 Mac 模式或藍牙連線，這種狀態下沒有編程介面。\n"
                    "請：1) 用 USB 線連接鍵盤（並關掉藍牙連線）\n"
                    "    2) 長按 Fn + 左Alt 3 秒切到 Windows 模式（指示燈閃一次）\n"
                    "改完再長按 Fn + 左Alt 3 秒切回 Mac 模式（閃兩次）。")
            if cfg:
                raise DeviceError("找到 NIZ 鍵盤，但找不到編程介面（interface 1）。用 --list 看看偵測到什麼。")
            raise DeviceError("找不到 NIZ 68EC 鍵盤。請用 USB 線連接，並切到 Windows 模式（長按 Fn + 左Alt 3 秒）。")
        self.dev = hid.device()
        try:
            self.dev.open_path(d["path"])
        except OSError as e:
            raise DeviceError(
                f"無法開啟裝置: {e}\n"
                "如果是權限問題：系統設定 → 隱私權與安全性 → 輸入監控，允許你的終端機 App，然後重開終端機。")
        self.info = d
        return self

    def close(self):
        if self.dev:
            self.dev.close()
            self.dev = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *a):
        self.close()

    # -- raw io ------------------------------------------------------------
    def send(self, packet):
        assert len(packet) == PKT
        if self.verbose:
            print(">>", packet.hex(), file=sys.stderr)
        n = self.dev.write(b"\x00" + bytes(packet))
        if n < 0:
            raise DeviceError("寫入 USB 失敗")

    def send_cmd(self, cmd, payload=b""):
        buf = bytearray(PKT)
        buf[1] = cmd
        buf[2:2 + len(payload)] = payload[:PKT - 2]
        self.send(bytes(buf))

    def recv(self, timeout_ms=1000):
        data = self.dev.read(PKT + 1, timeout_ms)
        if not data:
            return None
        data = bytes(data)
        if len(data) == PKT + 1:  # some backends keep the report ID
            data = data[1:]
        data = data.ljust(PKT, b"\x00")[:PKT]
        if self.verbose:
            print("<<", data.hex(), file=sys.stderr)
        return data

    def drain(self):
        while self.dev.read(PKT + 1, 50):
            pass

    # -- commands ----------------------------------------------------------
    def version(self):
        self.drain()
        self.send_cmd(CMD_VERSION)
        r = self.recv()
        if r is None:
            raise DeviceError("鍵盤沒有回應版本查詢")
        return r[2:].split(b"\x00")[0].decode("ascii", "replace").strip()

    def read_all(self, progress=None):
        self.drain()
        self.send_cmd(CMD_READ_ALL)
        slots = {}
        while True:
            r = self.recv(2000)
            if r is None:
                raise DeviceError("讀取鍵位時逾時（沒收到結束封包）")
            if r[0] == CMD_DATA_END:
                break
            if r[1] != CMD_KEY_DATA:
                continue
            packets = [r]
            if r[4] in (2, 3, 4):
                length = (r[9] << 8) | r[10]
                if length > MACRO_CHUNK:
                    extra = (length + MACRO_CHUNK - 1) // MACRO_CHUNK - 1
                    for _ in range(extra):
                        x = self.recv(2000)
                        if x is None:
                            raise DeviceError("讀取巨集資料時逾時")
                        packets.append(x)
            s = Slot(packets)
            if 1 <= s.layer <= LAYERS and 1 <= s.key <= KEYS_PER_LAYER:
                slots[(s.layer, s.key)] = s
            if progress:
                progress(len(slots))
        return slots

    def write_all(self, slots, progress=None):
        """Mirror of the official writeKeyConfigurationToDev: F1, then every
        one of the 9x68 slots in order, then an F6-filled end packet."""
        self.drain()
        self.send_cmd(CMD_WRITE_ALL)
        n = 0
        for layer in range(1, LAYERS + 1):
            for key in range(1, KEYS_PER_LAYER + 1):
                s = slots.get((layer, key))
                if s is None:
                    self.send(empty_slot_packet(layer, key))
                else:
                    for p in s.packets:
                        self.send(p)
                n += 1
                if progress:
                    progress(n)
                time.sleep(0.002)
        end = bytearray([CMD_DATA_END] * PKT)
        end[0] = 0x00
        self.send(bytes(end))

    def read_counter(self):
        self.drain()
        self.send_cmd(CMD_READ_COUNTER)
        raw = bytearray()
        while True:
            r = self.recv(2000)
            if r is None:
                raise DeviceError("讀取按鍵計數時逾時")
            if r[1] == CMD_COUNTER_END:
                break
            if r[1] == CMD_COUNTER_DATA:
                n = r[2]
                raw += r[3:3 + n]
        return [int.from_bytes(raw[i:i + 4], "little") for i in range(0, len(raw) - 3, 4)]


# --------------------------------------------------------------------------
# Backup helpers
# --------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(HERE, "backups")


def save_backup(slots, version, path=None):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    if path is None:
        ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = os.path.join(BACKUP_DIR, f"keymap-{ts}.json")
    data = {
        "format": "niz68-keymap-v1",
        "version": version,
        "saved_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "slots": {f"{l}:{k}": s.to_json() for (l, k), s in sorted(slots.items())},
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=1)
    return path


def load_backup(path):
    with open(path) as f:
        data = json.load(f)
    if data.get("format") != "niz68-keymap-v1":
        raise SystemExit("這不是 niz68 的備份檔")
    slots = {}
    for lk, pk in data["slots"].items():
        l, k = (int(x) for x in lk.split(":"))
        slots[(l, k)] = Slot.from_json(pk)
    return data, slots


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def bar(total, label):
    def f(n):
        w = 30
        done = int(w * min(n, total) / total)
        sys.stderr.write(f"\r{label} [{'#' * done}{'.' * (w - done)}] {n}/{total}")
        sys.stderr.flush()
    return f


def print_table(slots, layers, counts=None):
    keys = sorted({k for (_, k) in slots})
    hdr = ["Key"] + [f"L{l} {LAYER_NAMES.get(l, '')}".strip() for l in layers]
    if counts:
        hdr.append("Count")
    rows = []
    for k in keys:
        row = [str(k)]
        for l in layers:
            s = slots.get((l, k))
            row.append(s.describe() if s else "")
        if counts:
            row.append(str(counts[k - 1]) if k - 1 < len(counts) else "")
        rows.append(row)
    widths = [max(len(r[i]) for r in rows + [hdr]) for i in range(len(hdr))]
    line = "  ".join(h.ljust(w) for h, w in zip(hdr, widths))
    print(line)
    print("-" * len(line))
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)))


def used_layers(slots, show_all=False):
    return list(range(1, LAYERS + 1)) if show_all else [1, 2, 3]


def cmd_list(args):
    if hid is None:
        raise DeviceError("缺少 hidapi 套件，請先執行 ./setup.sh")
    cfg, macmode = find_devices()
    for d in cfg + macmode:
        print(f"{d['vendor_id']:04x}:{d['product_id']:04x} if={d.get('interface_number')} "
              f"usage={d.get('usage_page', 0):04x}:{d.get('usage', 0):04x} {d.get('product_string')!r}")
    if not cfg and not macmode:
        print("沒有偵測到 NIZ 鍵盤")


def cmd_info(args):
    with NiZ(args.verbose) as k:
        print("韌體版本:", k.version())


def cmd_read(args):
    with NiZ(args.verbose) as k:
        ver = k.version()
        print("韌體版本:", ver, file=sys.stderr)
        slots = k.read_all(bar(LAYERS * KEYS_PER_LAYER, "讀取鍵位"))
        print(file=sys.stderr)
        counts = k.read_counter() if args.counts else None
    path = save_backup(slots, ver, args.save)
    print(f"已備份到: {path}", file=sys.stderr)
    if args.raw:
        for (l, kk), s in sorted(slots.items()):
            for p in s.packets:
                print(f"L{l} K{kk:2d} {p.hex()}")
        return
    print_table(slots, used_layers(slots, args.all), counts)
    if not args.all:
        print("\n（只顯示第 1-3 層；用 --all 顯示全部 9 層）", file=sys.stderr)


def cmd_set(args):
    key = args.key
    layers = [int(x) for x in str(args.layer).split(",")]
    if not all(1 <= l <= LAYERS for l in layers) or not 1 <= key <= KEYS_PER_LAYER:
        raise SystemExit("layer 要 1-9，key 要 1-68")
    codes = [parse_code(c) for c in args.codes.split("+")]
    if len(codes) > 6:
        raise SystemExit("組合鍵太多")
    with NiZ(args.verbose) as k:
        ver = k.version()
        print("韌體版本:", ver)
        slots = k.read_all(bar(LAYERS * KEYS_PER_LAYER, "讀取目前鍵位"))
        print(file=sys.stderr)
        path = save_backup(slots, ver)
        print(f"修改前已備份到: {path}")
        changes = {}
        for layer in layers:
            old = slots.get((layer, key))
            new = Slot.normal(layer, key, codes)
            changes[(layer, key)] = new
            print(f"L{layer} K{key}: {(old.describe() if old else '') or '(空)'}  →  {new.describe() or '(空)'}")
            if old is not None and old.type != 0:
                print(f"  注意：這個鍵原本是 {TYPE_NAMES.get(old.type, old.type)}，會被改成一般按鍵")
        if not args.yes:
            if input("確定寫入鍵盤？(y/N) ").strip().lower() != "y":
                print("已取消，沒有寫入")
                return
        slots.update(changes)
        k.write_all(slots, bar(LAYERS * KEYS_PER_LAYER, "寫入"))
        print(file=sys.stderr)
        time.sleep(0.5)
        after = k.read_all()
        bad = [lk for lk, s in after.items() if s.packets != slots[lk].packets] if set(after) == set(slots) else ["count"]
        if not bad:
            print("寫入成功，已讀回驗證全部鍵位 ✓")
        else:
            print("⚠️ 寫入後讀回的值不同:", bad[:10])
            print(f"可用這個指令還原: ./niz68 restore {path}")


def cmd_restore(args):
    data, slots = load_backup(args.file)
    print(f"備份檔: {args.file}（{data.get('version')}，{data.get('saved_at')}，{len(slots)} 個鍵位）")
    with NiZ(args.verbose) as k:
        ver = k.version()
        if data.get("version") and data["version"] != ver:
            print(f"⚠️ 備份的韌體版本 ({data['version']}) 跟目前 ({ver}) 不同")
        cur = k.read_all()
        path = save_backup(cur, ver)
        print(f"還原前的目前狀態已備份到: {path}")
        if not args.yes and input("確定要用備份覆蓋鍵盤設定？(y/N) ").strip().lower() != "y":
            print("已取消")
            return
        k.write_all(slots, bar(LAYERS * KEYS_PER_LAYER, "寫入"))
        print(file=sys.stderr)
        time.sleep(0.5)
        after = k.read_all()
        diff = [lk for lk in set(slots) | set(after)
                if (slots.get(lk) and slots[lk].packets) != (after.get(lk) and after[lk].packets)]
        print("還原完成並已驗證 ✓" if not diff else f"⚠️ 有 {len(diff)} 個鍵位讀回不一致: {sorted(diff)[:10]}")


def cmd_codes(args):
    for c, n in sorted(CODES.items()):
        if n:
            print(f"{c:4d}  {n}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="niz68", description="NIZ 68EC 鍵盤 Mac 編程工具（鍵位）")
    p.add_argument("-v", "--verbose", action="store_true", help="顯示原始 USB 封包")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="列出偵測到的 NIZ 裝置").set_defaults(func=cmd_list)
    sub.add_parser("info", help="讀韌體版本").set_defaults(func=cmd_info)
    r = sub.add_parser("read", help="讀出目前所有鍵位（會自動備份）")
    r.add_argument("--counts", action="store_true", help="一起顯示按鍵次數")
    r.add_argument("--raw", action="store_true", help="輸出原始封包")
    r.add_argument("--save", help="備份檔路徑（預設存到 backups/）")
    r.add_argument("--all", action="store_true", help="顯示全部 9 層")
    r.set_defaults(func=cmd_read)
    s = sub.add_parser("set", help="改一個鍵: set <layer> <key> <code>，例如 set 1 30 CapsLock")
    s.add_argument("layer", help="層: 1=NoneFn 2=RightFn 3=LeftFn；可用逗號一次改多層，例如 1,4,7")
    s.add_argument("key", type=int, help="按鍵編號 1-68（看 read 的 Key 欄）")
    s.add_argument("codes", help="按鍵名稱或代碼，組合鍵用 + 連接，例如 LCtrl+C")
    s.add_argument("-y", "--yes", action="store_true", help="不詢問直接寫入")
    s.set_defaults(func=cmd_set)
    rs = sub.add_parser("restore", help="從備份檔還原全部鍵位")
    rs.add_argument("file")
    rs.add_argument("-y", "--yes", action="store_true")
    rs.set_defaults(func=cmd_restore)
    sub.add_parser("codes", help="列出可用的按鍵名稱與代碼").set_defaults(func=cmd_codes)
    args = p.parse_args(argv)
    try:
        args.func(args)
    except DeviceError as e:
        print("錯誤:", e, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
