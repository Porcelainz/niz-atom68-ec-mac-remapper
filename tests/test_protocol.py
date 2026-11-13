"""Simulate a 68EC on the HID protocol and exercise read / set / restore.

Run:  python3 tests/test_protocol.py
No keyboard or hidapi installation is needed.
"""
import sys, types, importlib.util, os, tempfile, io, contextlib
TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "niz68.py")

class FakeKB:
    def __init__(self):
        # layer1 normal keys, one macro on L2 K5 (2 packets), type0 on L3 K1
        self.slots = {}
        for l in range(1, 10):
            for k in range(1, 69):
                self.slots[(l,k)] = [self.normal(l,k,[k] if l % 3 == 1 else [])]
        m1 = bytearray(64); m1[1]=0xF0; m1[2]=2; m1[3]=5; m1[4]=2; m1[9]=0; m1[10]=60
        m1[11:64] = bytes(range(53)); m2 = bytearray(64); m2[0:7] = bytes(range(53,60))
        self.slots[(2,5)] = [bytes(m1), bytes(m2)]
        t1 = bytearray(64); t1[1]=0xF0; t1[2]=3; t1[3]=1; t1[4]=1; t1[5]=0; t1[6]=50; t1[7]=1; t1[8]=43
        self.slots[(3,1)] = [bytes(t1)]
        self.out = []; self.writing = None
    @staticmethod
    def normal(l,k,codes):
        b = bytearray(64); b[1]=0xF0; b[2]=l; b[3]=k; b[4]=0; b[5]=len(codes); b[6:6+len(codes)] = bytes(codes); return bytes(b)
    def write(self, data):
        assert len(data) == 65 and data[0] == 0, data
        p = bytes(data[1:]); cmd = p[1]
        if self.writing is not None:
            if p[1] == 0xF6 and all(x == 0xF6 for x in p[1:]):
                # rebuild
                new = {}; i = 0; pk = self.writing
                while i < len(pk):
                    h = pk[i]; packs=[h]; i += 1
                    if h[4] in (2,3,4):
                        ln = (h[9]<<8)|h[10]; extra = max(0,(ln+52)//53-1)
                        packs += pk[i:i+extra]; i += extra
                    new[(h[2],h[3])] = packs
                assert len([1 for x in pk if x[1]==0xF0 and x[4] in (0,1,2,3,4)]) >= 9*68 - 0
                self.slots = new; self.writing = None
            else:
                self.writing.append(p)
            return 65
        if cmd == 0xF9:
            self.out.append(b"\x00\xf9" + b"68EC(S)BLe;V1.4.6;V1.0;".ljust(62, b"\0"))
        elif cmd == 0xF2:
            for key in sorted(self.slots): self.out += self.slots[key]
            self.out.append(bytes([0xF6]*64))
        elif cmd == 0xF1:
            self.writing = []
        elif cmd == 0xE3:
            vals = b"".join((i*10).to_bytes(4,'little') for i in range(68))
            for off in range(0, len(vals), 60):
                ch = vals[off:off+60]; self.out.append(bytes([0,0xE3,len(ch)]) + ch + bytes(61-len(ch)))
            self.out.append(bytes([0,0xE6]) + bytes(62))
        return 65
    def read(self, n, timeout=0):
        return list(self.out.pop(0)) if self.out else []
    def open_path(self, p): pass
    def close(self): pass

kb = FakeKB()
fake = types.SimpleNamespace(
    enumerate=lambda: [{"vendor_id":0x0483,"product_id":0x5132,"interface_number":1,"usage_page":0xff00,"usage":1,"path":b"x","product_string":"NIZ"}],
    device=lambda: kb)
sys.modules["hid"] = fake
spec = importlib.util.spec_from_file_location("niz68", TOOL); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.BACKUP_DIR = tempfile.mkdtemp()
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    m.main(["read", "--counts"])
orig = {k: list(v) for k, v in kb.slots.items()}
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    m.main(["set", "1,4", "30", "LCtrl+C", "-y"])
for l in (1,4):
    h = kb.slots[(l,30)][0]; assert h[4]==0 and h[5]==2 and list(h[6:8])==[67,58], h.hex()
assert kb.slots[(2,5)] == orig[(2,5)], "macro not preserved"
assert kb.slots[(3,1)] == orig[(3,1)], "repeat key not preserved"
assert all(kb.slots[k]==orig[k] for k in orig if k not in ((1,30),(4,30)))
bk = sorted(os.listdir(m.BACKUP_DIR))[0]
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    m.main(["restore", os.path.join(m.BACKUP_DIR, bk), "-y"])
assert kb.slots == orig, "restore mismatch"
print("ALL MOCK TESTS PASSED")
