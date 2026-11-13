# NIZ 5th-gen (68EC) USB HID keymap protocol

Notes from analysing the official Windows programming software
(`68EC.exe` / `68ECHWI.dll`, V1.3.1), checked against a real
68EC(S)BLe board running firmware V1.4.5. Only the keymap, version and
press-counter commands are described here. The firmware update path exists
in the DLL but is deliberately left out of this project.

## Device

| Mode | VID | PID | Config interface |
|---|---|---|---|
| Windows mode, USB | `0x0483` | `0x5032` / `0x5132` / `0x5232` / `0x5332` | interface 1 (usage page `0x008C`) |
| Mac mode | `0x05AC` | `0x0220` / `0x022C` / `0x0252` | none usable for programming |

The board must be connected by USB and switched to Windows mode
(hold Fn + Left Alt for 3 s) before it exposes the config interface. Over
Bluetooth only the regular keyboard/consumer/mouse collections are present.

Verified on hardware: PID `0x5132` only.

## Framing

Every transfer is a 64-byte HID report with report ID `0`. On the wire the
host writes 65 bytes (`00` + 64 data bytes). Requests look like:

```
[0] 0x00
[1] command
[2..63] payload (zero-filled)
```

## Commands

| Cmd | Name | Notes |
|---|---|---|
| `F9` | version | reply `[0]=00 [1]=F9 [2..]` ASCII, e.g. `68EC(S)BLe;V1.4.5;V1.1;` |
| `F2` | read keymap | device streams key-slot packets, then a packet whose byte `[0]` is `F6` |
| `F1` | begin write | followed by key-slot packets for **every** slot, then an end packet |
| `F0` | key-slot data | see below |
| `F6` | end of data | host sends `[0]=00 [1..63]=F6` to finish a write |
| `E3` | read press counters | replies `[1]=E3 [2]=len [3..]` data, terminated by `[1]=E6` |

Press counters are little-endian `uint32`, one per key (68 values).

## Key-slot packet (`F0`)

```
[0] 0x00
[1] 0xF0
[2] layer   1..9
[3] key id  1..68
[4] type
```

The official software iterates 9 layers x 68 keys (612 slots) on both read
and write. On the tested board layers 4-6 and 7-9 are copies of 1-3. Layer
1 is the base layer (no Fn); layers 2 and 3 are the two Fn layers (believed
to be Right Fn and Left Fn respectively, by analogy with the 66EC; not yet
confirmed on the 68EC).

### Type 0 — normal key / key combination

```
[5]          n  (number of key codes, 0 = unassigned)
[6..6+n)     key codes
```

A single key has `n = 1`; a combination such as Ctrl+C has `n = 2`.
Every slot on a factory-default board is type 0.

### Type 1 — repeat key

```
[5..6]       parameter (big-endian; meaning not yet identified)
[7]          n
[8..8+n)     key codes
```

### Types 2, 3, 4 — macros

```
[9..10]      payload length L (big-endian)
[11..63]     first 53 bytes of payload
```

When `L > 53`, `ceil(L / 53) - 1` additional raw 64-byte packets follow
immediately. This project does not decode macro payloads; it stores and
re-sends them byte for byte so existing macros survive a keymap write.

## Write sequence

1. `F1`
2. For layer 1..9, for key 1..68: the slot's packet(s). Slots with no data
   are sent as `00 F0 <layer> <key> 00 00 ...`.
3. `00 F6 F6 ... F6` (63 bytes of `F6`)

## Key codes

See `CODES` in [`niz68.py`](../niz68.py). Codes `1..177` match the table
published in [cho45/niz-tools-ruby](https://github.com/cho45/niz-tools-ruby)
for the 66EC. The 68EC base layer read from hardware matched it exactly.
Codes 178, 198 and 207 appear on the factory Fn layer but are not yet named.
