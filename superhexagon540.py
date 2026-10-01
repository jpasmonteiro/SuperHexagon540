#!/usr/bin/env python3
"""Super Hexagon 540 Hz patcher v2.0 (Python version, patch v25).

Same behaviour as SuperHexagon540Patcher.exe, for people who prefer to read and run a script:
  python superhexagon540.py            interactive menu
  python superhexagon540.py --hz 540   apply at 540 Hz (any multiple of 60, 120..960)
  python superhexagon540.py --restore  restore the original from SuperHexagon.exe.bak
  python superhexagon540.py --status   show the current state
  python superhexagon540.py --lang pt  language: en or pt (default: system language)
Pass the game folder as an argument if the script is not inside it.
No network access, no admin rights. Only SuperHexagon.exe and SuperHexagon.exe.bak are touched.
"""
import base64, hashlib, os, shutil, struct, sys, zlib

ORIG_SHA = "72b0c26053c37edd3435def461e9027cd6ffad12032db2fd0b32c256fdbee6b9"
ORIG_SIZE = 1467904
PATCH_VERSION = 25
OFF_N, OFF_IDX, OFF_TABLE, OFF_VERSION = 8, 12, 96, 112

# Code detours in the original executable: (file offset, new bytes)
RUNS = [
    (310, bytes.fromhex("08")),
    (385, bytes.fromhex("0017")),
    (398, bytes.fromhex("00")),
    (792, bytes.fromhex("2e736835343064")),
    (801, bytes.fromhex("30")),
    (805, bytes.fromhex("b016")),
    (809, bytes.fromhex("30")),
    (813, bytes.fromhex("6616")),
    (828, bytes.fromhex("40")),
    (831, bytes.fromhex("c02e736835343063")),
    (841, bytes.fromhex("20")),
    (845, bytes.fromhex("e016")),
    (849, bytes.fromhex("20")),
    (853, bytes.fromhex("9616")),
    (868, bytes.fromhex("20")),
    (871, bytes.fromhex("60")),
    (18576, bytes.fromhex("e95f911600")),
    (96384, bytes.fromhex("e982611500909090")),
    (106269, bytes.fromhex("e9943b1500909090")),
    (106289, bytes.fromhex("e9b43b150090")),
    (106832, bytes.fromhex("e8b056")),
    (107001, bytes.fromhex("e8b056")),
    (107260, bytes.fromhex("e9223e1500909090909090909090")),
    (108403, bytes.fromhex("e9493b150090")),
    (108414, bytes.fromhex("e9563b1500909090")),
    (108639, bytes.fromhex("e99a3a1500909090")),
    (147155, bytes.fromhex("e989a4140090909090")),
    (147192, bytes.fromhex("e97ba4140090909090")),
    (147731, bytes.fromhex("e8fe961400909090909090")),
    (147883, bytes.fromhex("e897961400909090909090")),
    (148678, bytes.fromhex("c787705700000100")),
    (148688, bytes.fromhex("e87592140090909090909090")),
    (148764, bytes.fromhex("c78770570000ffffffffe85092140090909090909090")),
    (148932, bytes.fromhex("e8e39114009090909090909090909090")),
    (148996, bytes.fromhex("e8d89114009090909090909090909090")),
    (166275, bytes.fromhex("e9f04e140090")),
    (166648, bytes.fromhex("e9ae571400909090")),
    (166764, bytes.fromhex("e95b4f1400909090")),
    (167297, bytes.fromhex("e9074b1400909090909090")),
    (167391, bytes.fromhex("e94a51140090")),
    (167683, bytes.fromhex("e96c51140090909090909090")),
    (168173, bytes.fromhex("e9a64414009090909090909090")),
    (168235, bytes.fromhex("0d48b056")),
    (168247, bytes.fromhex("0f1f4000")),
    (168255, bytes.fromhex("0f1f4000")),
    (168267, bytes.fromhex("e9c945140090")),
    (168297, bytes.fromhex("0dd8b056")),
    (168305, bytes.fromhex("0f1f4000")),
    (168317, bytes.fromhex("0f1f4000")),
    (168453, bytes.fromhex("100548b056")),
    (168467, bytes.fromhex("e9804414009090909090")),
    (168592, bytes.fromhex("1005d8b056")),
    (168660, bytes.fromhex("e98d4b140090909090909090")),
    (168728, bytes.fromhex("e96b4b14009090909090909090909090909090909090")),
    (168802, bytes.fromhex("e94d4b14009090909090909090909090909090909090")),
    (168937, bytes.fromhex("e9f24a140090")),
    (169088, bytes.fromhex("e97d4a140090909090909090909090909090909090909090")),
    (169604, bytes.fromhex("e9904c14009090909090909090")),
    (169712, bytes.fromhex("e9484c14009090909090")),
    (169854, bytes.fromhex("e9e441140090909090")),
    (170448, bytes.fromhex("e9d63e14009090909090909090")),
    (173886, bytes.fromhex("e98c311400")),
    (174432, bytes.fromhex("e9a22f140090909090")),
    (176456, bytes.fromhex("e9d2271400909090909090909090909090")),
    (178623, bytes.fromhex("e9831f1400909090909090909090909090")),
    (180465, bytes.fromhex("e9ed1814009090")),
    (197776, bytes.fromhex("e97ccf1300909090")),
    (197920, bytes.fromhex("dd0518b056")),
    (203348, bytes.fromhex("a8b913"))
]
# Appended sections .sh540d (data) and .sh540c (code), zlib + base64.
# Their source is build540.py in the repository.
SECTIONS = (
    "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"
)

def sha(b): return hashlib.sha256(b).hexdigest()
def is_original(b): return len(b) == ORIG_SIZE and sha(b) == ORIG_SHA
def patched_info(b):
    if len(b) > ORIG_SIZE + 0x100 and b[ORIG_SIZE:ORIG_SIZE + 8] == b"SH540PAT":
        n, = struct.unpack_from("<i", b, ORIG_SIZE + OFF_N)
        v, = struct.unpack_from("<i", b, ORIG_SIZE + OFF_VERSION)
        return n, v
    return None

def table_for(n):
    base, extra = divmod(64, n); acc = 0; t = []
    for _ in range(n):
        acc += extra
        if acc >= n: acc -= n; t.append(base + 1)
        else: t.append(base)
    return t

def make_patched(orig, n):
    out = bytearray(orig)
    for off, data in RUNS: out[off:off + len(data)] = data
    sec = bytearray(zlib.decompress(base64.b64decode(SECTIONS)))
    struct.pack_into("<ii", sec, OFF_N, n, n - 1)
    sec[OFF_TABLE:OFF_TABLE + 16] = bytes(16)
    sec[OFF_TABLE:OFF_TABLE + n] = bytes(table_for(n))
    return bytes(out + sec)

def detect_lang():
    try:
        import ctypes
        if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3ff) == 0x16: return "pt"
        return "en"
    except Exception:
        pass
    import locale
    for v in (os.environ.get("LC_ALL"), os.environ.get("LANG"), (locale.getlocale()[0] or "")):
        if v: return "pt" if v.lower().startswith("pt") else "en"
    return "en"

LANG = detect_lang()
MSG = {
    "game": ("Game:", "Jogo:"),
    "state": ("State:", "Estado:"),
    "orig": ("original (60 Hz)", "original (60 Hz)"),
    "patched": ("patched at %d Hz", "modificado a %d Hz"),
    "old": ("patched at %d Hz with an older patch (v%d), apply again to update",
            "modificado a %d Hz com uma versão antiga do patch (v%d), aplique de novo para atualizar"),
    "unknown": ("unknown version (Steam update or modified by another tool)",
                "versão desconhecida (atualização do Steam ou modificado por outra ferramenta)"),
    "badrate": ("Rate must be a multiple of 60 between 120 and 960.", "A taxa precisa ser múltiplo de 60 entre 120 e 960."),
    "unsupported": ("Unsupported SuperHexagon.exe and no original backup. Verify the game files in Steam.",
                    "Este SuperHexagon.exe não é a versão suportada e não há backup original. Verifique os arquivos no Steam."),
    "backup": ("Backup created:", "Backup criado:"),
    "done": ("Done: game patched for %d Hz.", "Pronto: jogo modificado para %d Hz."),
    "already": ("Already original.", "O jogo já está original."),
    "nobackup": ("No original backup. Verify the game files in Steam.", "Backup original não encontrado. Verifique os arquivos no Steam."),
    "restored": ("Original restored (60 Hz).", "Original restaurado (60 Hz)."),
    "notfound": ("SuperHexagon.exe not found. Put this script in the game folder or pass the folder.",
                 "SuperHexagon.exe não encontrado. Coloque este script na pasta do jogo ou passe a pasta como argumento."),
    "menu": ("[1] Apply 540 Hz  [2] Other rate  [3] Restore original  [4] Idioma: Português  [0] Exit\n> ",
             "[1] Aplicar 540 Hz  [2] Outra taxa  [3] Restaurar original  [4] Language: English  [0] Sair\n> "),
    "rate": ("Rate in Hz: ", "Taxa em Hz: "),
}
def t(k): return MSG[k][1 if LANG == "pt" else 0]

def paths(arg):
    d = arg or os.path.dirname(os.path.abspath(__file__))
    exe = d if d.lower().endswith(".exe") else os.path.join(d, "SuperHexagon.exe")
    return exe, exe + ".bak"

def read(p):
    with open(p, "rb") as f: return f.read()

def status(exe):
    b = read(exe); info = patched_info(b)
    if is_original(b): return t("orig")
    if info and info[1] == PATCH_VERSION: return t("patched") % (info[0] * 60)
    if info: return t("old") % (info[0] * 60, info[1])
    return t("unknown")

def apply(exe, bak, hz):
    if hz % 60 or not 120 <= hz <= 960: print(t("badrate")); return
    cur = read(exe)
    if is_original(cur): orig = cur
    elif os.path.exists(bak) and is_original(read(bak)): orig = read(bak)
    else: print(t("unsupported")); return
    if not (os.path.exists(bak) and is_original(read(bak))):
        with open(bak, "wb") as f: f.write(orig)
        print(t("backup"), bak)
    data = make_patched(orig, hz // 60)
    with open(exe, "wb") as f: f.write(data)
    print(t("done") % hz)

def restore(exe, bak):
    if is_original(read(exe)): print(t("already")); return
    if not (os.path.exists(bak) and is_original(read(bak))): print(t("nobackup")); return
    shutil.copyfile(bak, exe); print(t("restored"))

def main():
    global LANG
    args = sys.argv[1:]; hz = None; mode = None; folder = None
    while args:
        a = args.pop(0)
        if a == "--hz": hz = int(args.pop(0))
        elif a == "--restore": mode = "restore"
        elif a == "--status": mode = "status"
        elif a == "--lang": LANG = "pt" if args.pop(0).lower().startswith("pt") else "en"
        else: folder = a
    print("SuperHexagon 540 Hz patcher v2.0 (Python, patch v%d)\n" % PATCH_VERSION)
    exe, bak = paths(folder)
    if not os.path.exists(exe): sys.exit(t("notfound"))
    if mode == "status": print(t("game"), exe); print(t("state"), status(exe)); return
    if mode == "restore": return restore(exe, bak)
    if hz: return apply(exe, bak, hz)
    while True:
        print(t("game"), exe); print(t("state"), status(exe))
        try: c = input(t("menu")).strip()
        except EOFError: return
        if c == "1": apply(exe, bak, 540)
        elif c == "2":
            try: apply(exe, bak, int(input(t("rate"))))
            except ValueError: print(t("badrate"))
        elif c == "3": restore(exe, bak)
        elif c == "4": LANG = "en" if LANG == "pt" else "pt"
        else: return
        print()

if __name__ == "__main__":
    main()
