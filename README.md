# niz68-mac

Remap keys on a **NIZ 68EC** (5th-gen, electro-capacitive) keyboard from
**macOS**. NIZ only ships a Windows programming tool; this project talks to the
keyboard directly over USB and gives you a visual editor in your browser.

[中文說明](#中文說明)

- Visual 68-key layout: click a key, pick what it should do, write to keyboard
- Base layer and both Fn layers, key combinations (e.g. Ctrl+C)
- Automatic backup before every write, read-back verification after
- Existing macros are preserved untouched
- Per-key press counters
- Command-line interface as well

The keymap is stored in the keyboard itself, so changes keep working on any
computer and over Bluetooth.

> **Not affiliated with NIZ.** The protocol was worked out from the official
> Windows software for interoperability. Firmware updates are intentionally not
> supported — use the official tool for that.

## Requirements

- macOS with Python 3.9+ (`python3`)
- A NIZ 68EC connected **by USB cable** and switched to **Windows mode**
  (hold <kbd>Fn</kbd> + <kbd>Left Alt</kbd> for 3 s; the indicator flashes once).
  Mac mode and Bluetooth do not expose the programming interface.
  Switch back to Mac mode the same way afterwards (indicator flashes twice).

## Quick start

```bash
git clone https://github.com/Porcelainz/niz-atom68-ec-mac-remapper.git niz68-mac
cd niz68-mac
./setup.sh          # creates .venv and installs hidapi (once)
./niz68 gui         # opens the editor in your browser
```

Or double-click **`開啟改鍵工具.command`** in Finder. If macOS blocks it the
first time, right-click → Open → Open.

Try the interface without a keyboard: `./niz68 gui --demo`.

If opening the device fails with a permission error, allow your terminal app
under System Settings → Privacy & Security → Input Monitoring.

## Command line

| Command | |
|---|---|
| `./niz68 list` | list detected NIZ devices |
| `./niz68 info` | firmware version |
| `./niz68 read [--all] [--counts]` | show the keymap (backs it up to `backups/`) |
| `./niz68 set <layers> <key> <code>` | change one key, e.g. `./niz68 set 1,4,7 31 LCtrl` |
| `./niz68 restore backups/<file>.json` | write a backup back |
| `./niz68 codes` | list key names and codes |

Layers: `1` base, `2` Right Fn, `3` Left Fn. The keyboard stores 9 layers;
4–6 and 7–9 are copies of 1–3, so changing `1,4,7` together is recommended.
Combinations are joined with `+`, e.g. `LCtrl+C`.

## Compatibility

| | Status |
|---|---|
| 68EC, PID `0x5132`, firmware V1.4.5 | read, write and restore verified on hardware |
| 68EC, PIDs `0x5032` / `0x5232` / `0x5332` | recognised (same as official tool), not tested |
| Other NIZ models (66EC, 82EC, …) | not supported: different key counts/PIDs |

Unknown / help wanted:
- which of layers 4–9 are used in which mode
- whether layer 2 is Right Fn and layer 3 Left Fn on the 68EC (true on the 66EC)
- names for codes 178, 198 and 207
- editing macros and lighting

## How it works

See [docs/PROTOCOL.md](docs/PROTOCOL.md). The GUI is a small local web server
(`gui.py`) bound to `127.0.0.1` that requires a random per-launch token, so
other web pages cannot reach it. Tests run against a simulated keyboard:
`python3 tests/test_protocol.py`.

## Credits

Key code names are based on the table in
[cho45/niz-tools-ruby](https://github.com/cho45/niz-tools-ruby), which
documented the 66EC protocol. Protocol details for the 68EC were derived from
NIZ's official software and confirmed on hardware.

## License

MIT

---

## 中文說明

在 **macOS** 上替 **NIZ 寧芝 68EC**（五代靜電容）鍵盤改鍵。官方編程軟體只有
Windows 版，這個工具直接透過 USB 跟鍵盤溝通，並提供瀏覽器裡的圖形介面。
設定會存在鍵盤裡，換電腦或用藍牙都有效。

**本專案與 NIZ 官方無關**，不支援韌體更新，韌體請用官方軟體。

### 使用前準備

1. 用 **USB 線**連接鍵盤，並關掉藍牙連線
2. 長按 <kbd>Fn</kbd> + <kbd>左 Alt</kbd> 3 秒切到 **Windows 模式**（指示燈閃一次）
3. 改完再長按同一組合 3 秒切回 Mac 模式（閃兩次）

### 圖形介面

在 Finder 裡雙擊 **`開啟改鍵工具.command`**（第一次會自動安裝需要的套件）。
macOS 若擋下，在檔案上按右鍵 → 打開 → 打開。

1. 上方切換「一般層／右 Fn 層／左 Fn 層」
2. 點鍵盤上的鍵，從下方清單選要改成的鍵（可搜尋；勾「組合鍵模式」可組成 Ctrl+C）
3. 修改會先標成橘色暫存，確認後按「寫入鍵盤」
4. 「備份與還原」可以回到任何一次的設定，最早那份就是你原本的設定

想先試用介面又不碰鍵盤：`./niz68 gui --demo`。

### 指令列

```bash
./setup.sh                     # 第一次使用
./niz68 read                   # 看目前鍵位（自動備份到 backups/）
./niz68 set 1,4,7 31 LCtrl     # 把 CapsLock 改成左 Ctrl（三份一般層一起改）
./niz68 restore backups/xxx.json
./niz68 codes                  # 按鍵名稱清單
```

層：1 = 一般層，2 = 右 Fn 層，3 = 左 Fn 層。鍵盤內第 4–6、7–9 層是 1–3 層的複本，
建議一起改。

### 安全機制

- 每次寫入前自動備份完整設定，寫完讀回逐一驗證
- 原有的巨集與特殊鍵會原封不動保留，只改你指定的鍵
- 如果打開裝置時出現權限錯誤：系統設定 → 隱私權與安全性 → 輸入監控，允許你的終端機 App
