import io
import json
import os
import posixpath
import re
import shutil
import tempfile
import urllib.request
from copy import deepcopy
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QApplication, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea,
    QTextEdit, QVBoxLayout, QWidget, QInputDialog
)

COLLECTIONS_REL = Path("Scripts/.config/CollectionLauncher/Collections")
COLLECTIONS_REMOTE = "/media/fat/Scripts/.config/CollectionLauncher/Collections"
ONLINE_GAME_ROOTS = [
    ("SD Card", "/media/fat/games"),
    ("Network / CIFS", "/media/fat/cifs/games"),
    ("USB", "/media/usb0/games"),
]
ONLINE_ARCADE_ROOTS = [
    ("SD Card", "/media/fat/_Arcade"),
    ("USB", "/media/usb0/_Arcade"),
]
SYSTEM_PRESETS = {'AdventureVision': {'aliases': ['AVision', 'Adventure Vision'], 'variants': [{'role': 'game', 'label': 'Game', 'exts': ['.bin'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'Amiga': {'aliases': ['Minimig', 'Amiga'], 'variants': [{'role': 'floppy1', 'label': 'df0', 'exts': ['.adf'], 'delay': 1, 'type': 'f', 'index': 0}]}, 'AmigaCD32': {'aliases': ['AmigaCD32', 'Amiga CD32'], 'variants': [{'role': 'cd', 'label': 'CD Image', 'exts': ['.cue', '.chd'], 'delay': 1, 'type': 's', 'index': 1}]}, 'Amstrad': {'aliases': ['Amstrad CPC'], 'variants': [{'role': 'floppy1', 'label': 'A:', 'exts': ['.dsk'], 'delay': 1, 'type': 's', 'index': 0}, {'role': 'floppy2', 'label': 'B:', 'exts': ['.dsk'], 'delay': 1, 'type': 's', 'index': 1}, {'role': 'expansion', 'label': 'Expansion', 'exts': ['.e??'], 'delay': 1, 'type': 'f', 'index': 3}, {'role': 'tape', 'label': 'Tape', 'exts': ['.cdt'], 'delay': 1, 'type': 'f', 'index': 4}]}, 'AmstradPCW': {'aliases': ['Amstrad-PCW', 'Amstrad PCW'], 'variants': [{'role': 'floppy1', 'label': 'A:', 'exts': ['.dsk'], 'delay': 1, 'type': 's', 'index': 0}, {'role': 'floppy2', 'label': 'B:', 'exts': ['.dsk'], 'delay': 1, 'type': 's', 'index': 1}]}, 'Apogee': {'aliases': ['Apogee BK-01'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.rka', '.rkr', '.gam'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'AppleI': {'aliases': ['Apple-I', 'Apple I'], 'variants': [{'role': 'ascii', 'label': 'ASCII', 'exts': ['.txt'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'AppleII': {'aliases': ['Apple-II', 'Apple IIe'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.nib', '.dsk', '.do', '.po'], 'delay': 1, 'type': 's', 'index': 0}, {'role': 'game', 'label': '-', 'exts': ['.hdv'], 'delay': 1, 'type': 's', 'index': 1}]}, 'Arcadia': {'aliases': ['Arcadia 2001'], 'variants': [{'role': 'cart', 'label': 'Cartridge', 'exts': ['.bin'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'Arduboy': {'aliases': ['Arduboy'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.bin', '.hex'], 'delay': 1, 'type': 'f', 'index': 0}]}, 'Atari2600': {'aliases': ['Atari 2600'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.a26'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'Atari5200': {'aliases': ['Atari 5200'], 'variants': [{'role': 'cart', 'label': 'Cart', 'exts': ['.car', '.a52', '.bin', '.rom'], 'delay': 1, 'type': 's', 'index': 1}]}, 'Atari7800': {'aliases': ['Atari 7800'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.a78', '.bin'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'Atari800': {'aliases': ['Atari 800XL'], 'variants': [{'role': 'd1', 'label': 'D1', 'exts': ['.atr', '.xex', '.xfd', '.atx'], 'delay': 1, 'type': 's', 'index': 0}, {'role': 'd2', 'label': 'D2', 'exts': ['.atr', '.xex', '.xfd', '.atx'], 'delay': 1, 'type': 's', 'index': 1}, {'role': 'cart', 'label': 'Cartridge', 'exts': ['.car', '.rom', '.bin'], 'delay': 1, 'type': 's', 'index': 2}]}, 'AtariLynx': {'aliases': ['Atari Lynx'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.lnx'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'AcornAtom': {'aliases': ['Atom'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.vhd'], 'delay': 1, 'type': 's', 'index': 1}]}, 'BBCMicro': {'aliases': ['BBC Micro/Master'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.vhd'], 'delay': 1, 'type': 's', 'index': 0}, {'role': 'game', 'label': '-', 'exts': ['.ssd', '.dsd'], 'delay': 1, 'type': 's', 'index': 1}, {'role': 'game', 'label': '-', 'exts': ['.ssd', '.dsd'], 'delay': 1, 'type': 's', 'index': 2}]}, 'BK0011M': {'aliases': ['BK0011M'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.bin'], 'delay': 1, 'type': 'f', 'index': 1}, {'role': 'fdda', 'label': 'FDD(A)', 'exts': ['.dsk'], 'delay': 1, 'type': 's', 'index': 1}, {'role': 'fddb', 'label': 'FDD(B)', 'exts': ['.dsk'], 'delay': 1, 'type': 's', 'index': 2}, {'role': 'hdd', 'label': 'HDD', 'exts': ['.vhd'], 'delay': 1, 'type': 's', 'index': 0}]}, 'Astrocade': {'aliases': ['Bally Astrocade'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.bin'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'CDI': {'aliases': ['CD-I'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.cue', '.chd'], 'delay': 1, 'type': 's', 'index': 1}]}, 'Chip8': {'aliases': ['CHIP-8'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.ch8'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'CasioPV1000': {'aliases': ['Casio_PV-1000', 'Casio PV-1000'], 'variants': [{'role': 'cart', 'label': 'Cartridge', 'exts': ['.bin'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'CasioPV2000': {'aliases': ['Casio_PV-2000', 'Casio PV-2000'], 'variants': [{'role': 'cart', 'label': 'Cartridge', 'exts': ['.bin'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'ChannelF': {'aliases': ['Channel F'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.rom', '.bin'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'ColecoVision': {'aliases': ['Coleco', 'ColecoVision'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.col', '.bin', '.rom'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'C16': {'aliases': ['Commodore 16'], 'variants': [{'role': '8', 'label': '#8', 'exts': ['.d64', '.g64'], 'delay': 1, 'type': 's', 'index': 0}, {'role': '9', 'label': '#9', 'exts': ['.d64', '.g64'], 'delay': 1, 'type': 's', 'index': 1}, {'role': 'game', 'label': '-', 'exts': ['.prg', '.tap', '.bin'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'C64': {'aliases': ['Commodore 64'], 'variants': [{'role': '8', 'label': '#8', 'exts': ['.d64', '.g64', '.t64', '.d81'], 'delay': 1, 'type': 's', 'index': 0}, {'role': '9', 'label': '#9', 'exts': ['.d64', '.g64', '.t64', '.d81'], 'delay': 1, 'type': 's', 'index': 1}, {'role': 'game', 'label': '-', 'exts': ['.prg', '.crt', '.reu', '.tap'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'PET2001': {'aliases': ['Commodore PET 2001'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.prg', '.tap'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'VIC20': {'aliases': ['Commodore VIC-20'], 'variants': [{'role': '8', 'label': '#8', 'exts': ['.d64', '.g64'], 'delay': 1, 'type': 's', 'index': 0}, {'role': '9', 'label': '#9', 'exts': ['.d64', '.g64'], 'delay': 1, 'type': 's', 'index': 1}, {'role': 'game', 'label': '-', 'exts': ['.prg', '.crt', '.ct?', '.tap'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'EDSAC': {'aliases': ['EDSAC'], 'variants': [{'role': 'tape', 'label': 'Tape', 'exts': ['.tap'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'AcornElectron': {'aliases': ['Electron'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.vhd'], 'delay': 1, 'type': 's', 'index': 0}]}, 'FDS': {'aliases': ['FamicomDiskSystem', 'Famicom Disk System'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.fds'], 'delay': 2, 'type': 'f', 'index': 1}]}, 'Galaksija': {'aliases': ['Galaksija'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.tap'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'Gamate': {'aliases': ['Gamate'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.bin'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'GameNWatch': {'aliases': ['Game & Watch'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.bin'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'GameGear': {'aliases': ['GG', 'Game Gear'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.gg'], 'delay': 1, 'type': 'f', 'index': 2}]}, 'Gameboy': {'aliases': ['GB', 'Gameboy'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.gb'], 'delay': 2, 'type': 'f', 'index': 1}]}, 'Gameboy2P': {'aliases': ['Gameboy (2 Player)'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.gb', '.gbc'], 'delay': 2, 'type': 'f', 'index': 1}]}, 'GBA': {'aliases': ['GameboyAdvance', 'Gameboy Advance'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.gba'], 'delay': 2, 'type': 'f', 'index': 1}]}, 'GBA2P': {'aliases': ['Gameboy Advance (2 Player)'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.gba'], 'delay': 2, 'type': 'f', 'index': 1}]}, 'GameboyColor': {'aliases': ['GBC', 'Gameboy Color'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.gbc'], 'delay': 2, 'type': 'f', 'index': 1}]}, 'Genesis': {'aliases': ['MegaDrive', 'Genesis'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.bin', '.gen', '.md'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'Sega32X': {'aliases': ['S32X', '32X', 'Genesis 32X'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.32x'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'Groovy': {'aliases': ['Groovy'], 'variants': [{'role': 'gmc', 'label': 'GMC', 'exts': ['.gmc'], 'delay': 3, 'type': 'f', 'index': 1}]}, 'Intellivision': {'aliases': ['Intellivision'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.int', '.bin'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'Interact': {'aliases': ['Interact'], 'variants': [{'role': 'tape', 'label': 'Tape', 'exts': ['.cin', '.k7'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'Jaguar': {'aliases': ['Jaguar'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.jag', '.j64', '.rom', '.bin'], 'delay': 1, 'type': 's', 'index': 1}]}, 'Jupiter': {'aliases': ['Jupiter Ace'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.ace'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'Laser': {'aliases': ['Laser310', 'Laser 350/500/700'], 'variants': [{'role': 'vzimage', 'label': 'VZ Image', 'exts': ['.vz'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'Lynx48': {'aliases': ['Lynx 48/96K'], 'variants': [{'role': 'tape', 'label': 'Cassette', 'exts': ['.tap'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'SordM5': {'aliases': ['Sord M5', 'M5'], 'variants': [{'role': 'rom', 'label': 'ROM', 'exts': ['.bin', '.rom'], 'delay': 1, 'type': 'f', 'index': 1}, {'role': 'tape', 'label': 'Tape', 'exts': ['.cas'], 'delay': 1, 'type': 'f', 'index': 2}]}, 'MSX': {'aliases': ['MSX'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.vhd'], 'delay': 1, 'type': 's', 'index': 1}]}, 'MSX1': {'aliases': ['MSX1'], 'variants': [{'role': 'floppy1', 'label': 'Drive A:', 'exts': ['.dsk'], 'delay': 1, 'type': 's', 'index': 1}, {'role': 'slota', 'label': 'SLOT A', 'exts': ['.rom'], 'delay': 1, 'type': 'f', 'index': 2}, {'role': 'slotb', 'label': 'SLOT B', 'exts': ['.rom'], 'delay': 1, 'type': 'f', 'index': 3}]}, 'MacPlus': {'aliases': ['Macintosh Plus'], 'variants': [{'role': 'prifloppy', 'label': 'Pri Floppy', 'exts': ['.dsk'], 'delay': 1, 'type': 'f', 'index': 1}, {'role': 'secfloppy', 'label': 'Sec Floppy', 'exts': ['.dsk'], 'delay': 1, 'type': 'f', 'index': 2}, {'role': 'scsi6', 'label': 'SCSI-6', 'exts': ['.img', '.vhd'], 'delay': 1, 'type': 's', 'index': 0}, {'role': 'scsi5', 'label': 'SCSI-5', 'exts': ['.img', '.vhd'], 'delay': 1, 'type': 's', 'index': 1}]}, 'Odyssey2': {'aliases': ['Magnavox Odyssey2'], 'variants': [{'role': 'cart', 'label': 'Cartridge', 'exts': ['.bin'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'MasterSystem': {'aliases': ['SMS', 'Master System'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.sms'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'Aquarius': {'aliases': ['Mattel Aquarius'], 'variants': [{'role': 'cart', 'label': 'Cartridge', 'exts': ['.bin'], 'delay': 1, 'type': 'f', 'index': 1}, {'role': 'tape', 'label': 'Tape', 'exts': ['.caq'], 'delay': 1, 'type': 'f', 'index': 2}]}, 'MegaDuck': {'aliases': ['Mega Duck'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.bin'], 'delay': 2, 'type': 'f', 'index': 1}]}, 'MultiComp': {'aliases': ['MultiComp'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.img'], 'delay': 1, 'type': 's', 'index': 1}]}, 'NES': {'aliases': ['NES'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.nes'], 'delay': 2, 'type': 'f', 'index': 1}]}, 'NESMusic': {'aliases': ['NES Music'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.nsf'], 'delay': 2, 'type': 'f', 'index': 1}]}, 'NeoGeoCD': {'aliases': ['Neo Geo CD'], 'variants': [{'role': 'cd', 'label': 'CD Image', 'exts': ['.cue', '.chd'], 'delay': 1, 'type': 's', 'index': 1}]}, 'NeoGeo': {'aliases': ['Neo Geo MVS/AES'], 'variants': [{'role': 'cart', 'label': 'ROM set', 'exts': ['.neo'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'Nintendo64': {'aliases': ['N64', 'Nintendo 64'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.n64', '.z64'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'Orao': {'aliases': ['Orao'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.tap'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'Oric': {'aliases': ['Oric'], 'variants': [{'role': 'floppy1', 'label': 'Drive A:', 'exts': ['.dsk'], 'delay': 1, 'type': 's', 'index': 0}]}, 'ao486': {'aliases': ['PC (486SX)'], 'variants': [{'role': 'floppy1', 'label': 'Floppy A:', 'exts': ['.img', '.ima', '.vfd'], 'delay': 1, 'type': 's', 'index': 0}, {'role': 'hdd', 'label': 'IDE 0-0', 'exts': ['.vhd'], 'delay': 1, 'type': 's', 'index': 2}, {'role': 'cd', 'label': 'CD', 'exts': ['.iso'], 'delay': 1, 'type': 's', 'index': 4}]}, 'PCXT': {'aliases': ['PC/XT'], 'variants': [{'role': 'floppy1', 'label': 'Floppy A:', 'exts': ['.img', '.ima', '.vfd'], 'delay': 1, 'type': 's', 'index': 0}, {'role': 'floppy2', 'label': 'Floppy B:', 'exts': ['.img', '.ima', '.vfd'], 'delay': 1, 'type': 's', 'index': 1}, {'role': 'hdd', 'label': 'IDE 0-0', 'exts': ['.vhd'], 'delay': 1, 'type': 's', 'index': 2}, {'role': 'hdd2', 'label': 'IDE 0-1', 'exts': ['.vhd'], 'delay': 1, 'type': 's', 'index': 3}]}, 'PDP1': {'aliases': ['PDP-1'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.pdp', '.rim', '.bin'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'PMD85': {'aliases': ['PMD 85-2A'], 'variants': [{'role': 'rompack', 'label': 'ROM Pack', 'exts': ['.rmm'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'PSX': {'aliases': ['Playstation', 'PS1'], 'variants': [{'role': 'cd', 'label': 'CD', 'exts': ['.cue', '.chd'], 'delay': 1, 'type': 's', 'index': 1}, {'role': 'exe', 'label': 'Exe', 'exts': ['.exe'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'PocketChallengeV2': {'aliases': ['Pocket Challenge V2'], 'variants': [{'role': 'rom', 'label': 'ROM', 'exts': ['.pc2'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'PokemonMini': {'aliases': ['Pokemon Mini'], 'variants': [{'role': 'rom', 'label': 'ROM', 'exts': ['.min'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'RX78': {'aliases': ['RX-78 Gundam'], 'variants': [{'role': 'cart', 'label': 'Cartridge', 'exts': ['.bin'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'SAMCoupe': {'aliases': ['SAM Coupe'], 'variants': [{'role': 'drive1', 'label': 'Drive 1', 'exts': ['.dsk', '.mgt', '.img'], 'delay': 1, 'type': 's', 'index': 0}, {'role': 'drive2', 'label': 'Drive 2', 'exts': ['.dsk', '.mgt', '.img'], 'delay': 1, 'type': 's', 'index': 1}]}, 'SG1000': {'aliases': ['SG-1000'], 'variants': [{'role': 'sg1000', 'label': 'SG-1000', 'exts': ['.sg'], 'delay': 1, 'type': 'f', 'index': 0}]}, 'SNES': {'aliases': ['SuperNintendo', 'SNES'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.sfc', '.smc', '.bin', '.bs'], 'delay': 2, 'type': 'f', 'index': 0}]}, 'SNESMusic': {'aliases': ['SNES Music'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.spc'], 'delay': 2, 'type': 'f', 'index': 1}]}, 'SVI328': {'aliases': ['SV-328'], 'variants': [{'role': 'cart', 'label': 'Cartridge', 'exts': ['.bin', '.rom'], 'delay': 1, 'type': 'f', 'index': 1}, {'role': 'casfile', 'label': 'CAS File', 'exts': ['.cas'], 'delay': 1, 'type': 'f', 'index': 2}]}, 'Saturn': {'aliases': ['Saturn'], 'variants': [{'role': 'disk', 'label': 'Disk', 'exts': ['.cue', '.chd'], 'delay': 1, 'type': 's', 'index': 0}]}, 'MegaCD': {'aliases': ['SegaCD', 'Sega CD'], 'variants': [{'role': 'disk', 'label': 'Disk', 'exts': ['.cue', '.chd'], 'delay': 1, 'type': 's', 'index': 0}]}, 'QL': {'aliases': ['Sinclair QL'], 'variants': [{'role': 'hdd', 'label': 'HD Image', 'exts': ['.win'], 'delay': 1, 'type': 's', 'index': 0}, {'role': 'mdvimage', 'label': 'MDV Image', 'exts': ['.mdv'], 'delay': 1, 'type': 'f', 'index': 2}]}, 'Specialist': {'aliases': ['SPMX', 'Specialist/MX'], 'variants': [{'role': 'tape', 'label': 'Tape', 'exts': ['.rks'], 'delay': 1, 'type': 'f', 'index': 0}, {'role': 'disk', 'label': 'Disk', 'exts': ['.odi'], 'delay': 1, 'type': 's', 'index': 0}]}, 'SuperGameboy': {'aliases': ['SGB', 'Super Gameboy'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.gb', '.gbc'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'SuperGrafx': {'aliases': ['SuperGrafx'], 'variants': [{'role': 'supergrafx', 'label': 'SuperGrafx', 'exts': ['.sgx'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'SuperVision': {'aliases': ['SuperVision'], 'variants': [{'role': 'cart', 'label': 'Cartridge', 'exts': ['.bin', '.sv'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'TI994A': {'aliases': ['TI-99_4A', 'TI-99/4A'], 'variants': [{'role': 'fullcart', 'label': 'Full Cart', 'exts': ['.m99', '.bin'], 'delay': 1, 'type': 'f', 'index': 1}, {'role': 'romcart', 'label': 'ROM Cart', 'exts': ['.bin'], 'delay': 1, 'type': 'f', 'index': 2}, {'role': 'gromcart', 'label': 'GROM Cart', 'exts': ['.bin'], 'delay': 1, 'type': 'f', 'index': 3}]}, 'TRS80': {'aliases': ['TRS-80'], 'variants': [{'role': 'floppy1', 'label': 'Disk 0', 'exts': ['.dsk', '.jvi'], 'delay': 1, 'type': 's', 'index': 0}, {'role': 'floppy2', 'label': 'Disk 1', 'exts': ['.dsk', '.jvi'], 'delay': 1, 'type': 's', 'index': 1}, {'role': 'program', 'label': 'Program', 'exts': ['.cmd'], 'delay': 1, 'type': 'f', 'index': 2}, {'role': 'tape', 'label': 'Cassette', 'exts': ['.cas'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'CoCo2': {'aliases': ['TRS-80 CoCo 2'], 'variants': [{'role': 'cart', 'label': 'Cartridge', 'exts': ['.rom', '.ccc'], 'delay': 1, 'type': 'f', 'index': 1}, {'role': 'diskdrive0', 'label': 'Disk Drive 0', 'exts': ['.dsk'], 'delay': 1, 'type': 's', 'index': 0}, {'role': 'diskdrive1', 'label': 'Disk Drive 1', 'exts': ['.dsk'], 'delay': 1, 'type': 's', 'index': 1}, {'role': 'diskdrive2', 'label': 'Disk Drive 2', 'exts': ['.dsk'], 'delay': 1, 'type': 's', 'index': 2}, {'role': 'diskdrive3', 'label': 'Disk Drive 3', 'exts': ['.dsk'], 'delay': 1, 'type': 's', 'index': 3}, {'role': 'tape', 'label': 'Cassette', 'exts': ['.cas'], 'delay': 1, 'type': 'f', 'index': 2}]}, 'ZX81': {'aliases': ['TS-1500'], 'variants': [{'role': 'tape', 'label': 'Tape', 'exts': ['.0', '.p'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'TSConf': {'aliases': ['TS-Config'], 'variants': [{'role': 'virtualsd', 'label': 'Virtual SD', 'exts': ['.vhd'], 'delay': 1, 'type': 's', 'index': 0}]}, 'AliceMC10': {'aliases': ['Tandy MC-10'], 'variants': [{'role': 'tape', 'label': 'Tape', 'exts': ['.c10'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'TatungEinstein': {'aliases': ['Tatung Einstein'], 'variants': [{'role': 'floppy1', 'label': 'Disk 0', 'exts': ['.dsk'], 'delay': 1, 'type': 's', 'index': 0}]}, 'TurboGrafx16': {'aliases': ['TGFX16', 'PCEngine', 'TurboGrafx-16'], 'variants': [{'role': 'turbografx', 'label': 'TurboGrafx', 'exts': ['.bin', '.pce'], 'delay': 1, 'type': 'f', 'index': 0}]}, 'TurboGrafx16CD': {'aliases': ['TGFX16-CD', 'PCEngineCD', 'TurboGrafx-16 CD'], 'variants': [{'role': 'cd', 'label': 'CD', 'exts': ['.cue', '.chd'], 'delay': 1, 'type': 's', 'index': 0}]}, 'TomyTutor': {'aliases': ['Tutor'], 'variants': [{'role': 'cart', 'label': 'Cartridge', 'exts': ['.bin'], 'delay': 1, 'type': 'f', 'index': 2}, {'role': 'tapeimage', 'label': 'Tape Image', 'exts': ['.cas'], 'delay': 1, 'type': 's', 'index': 0}]}, 'UK101': {'aliases': ['UK101'], 'variants': [{'role': 'ascii', 'label': 'ASCII', 'exts': ['.txt', '.bas', '.lod'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'VC4000': {'aliases': ['VC4000'], 'variants': [{'role': 'cart', 'label': 'Cartridge', 'exts': ['.bin'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'CreatiVision': {'aliases': ['VTech CreatiVision'], 'variants': [{'role': 'cart', 'label': 'Cartridge', 'exts': ['.rom', '.bin'], 'delay': 1, 'type': 'f', 'index': 1}, {'role': 'basic', 'label': 'BASIC', 'exts': ['.bas'], 'delay': 1, 'type': 'f', 'index': 3}]}, 'Vector06C': {'aliases': ['Vector06', 'Vector-06C'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.rom', '.com', '.c00', '.edd'], 'delay': 1, 'type': 'f', 'index': 1}, {'role': 'diska', 'label': 'Disk A', 'exts': ['.fdd'], 'delay': 1, 'type': 's', 'index': 0}, {'role': 'diskb', 'label': 'Disk B', 'exts': ['.fdd'], 'delay': 1, 'type': 's', 'index': 1}]}, 'Vectrex': {'aliases': ['Vectrex'], 'variants': [{'role': 'game', 'label': '-', 'exts': ['.vec', '.bin', '.rom'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'WonderSwan': {'aliases': ['WonderSwan'], 'variants': [{'role': 'rom', 'label': 'ROM', 'exts': ['.ws'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'WonderSwanColor': {'aliases': ['WonderSwan Color'], 'variants': [{'role': 'rom', 'label': 'ROM', 'exts': ['.wsc'], 'delay': 1, 'type': 'f', 'index': 1}]}, 'X68000': {'aliases': ['X68000'], 'variants': [{'role': 'floppy1', 'label': 'FDD0', 'exts': ['.d88'], 'delay': 1, 'type': 's', 'index': 0}, {'role': 'floppy2', 'label': 'FDD1', 'exts': ['.d88'], 'delay': 1, 'type': 's', 'index': 1}, {'role': 'hdd', 'label': 'SASI Hard Disk', 'exts': ['.hdf'], 'delay': 1, 'type': 's', 'index': 2}, {'role': 'ram', 'label': 'RAM', 'exts': ['.ram'], 'delay': 1, 'type': 's', 'index': 3}]}, 'ZXSpectrum': {'aliases': ['Spectrum', 'ZX Spectrum'], 'variants': [{'role': 'disk', 'label': 'Disk', 'exts': ['.trd', '.img', '.dsk', '.mgt'], 'delay': 1, 'type': 's', 'index': 0}, {'role': 'tape', 'label': 'Tape', 'exts': ['.tap', '.csw', '.tzx'], 'delay': 1, 'type': 'f', 'index': 2}, {'role': 'snapshot', 'label': 'Snapshot', 'exts': ['.z80', '.sna'], 'delay': 1, 'type': 'f', 'index': 4}, {'role': 'divmmc', 'label': 'DivMMC', 'exts': ['.vhd'], 'delay': 1, 'type': 's', 'index': 1}]}, 'ZXNext': {'aliases': ['ZX Spectrum Next'], 'variants': [{'role': 'c', 'label': 'C:', 'exts': ['.vhd'], 'delay': 1, 'type': 's', 'index': 0}, {'role': 'd', 'label': 'D:', 'exts': ['.vhd'], 'delay': 1, 'type': 's', 'index': 1}, {'role': 'tape', 'label': 'Tape', 'exts': ['.tzx', '.csw'], 'delay': 1, 'type': 'f', 'index': 1}]}}
SYSTEM_PRESETS["Arcade"] = {"aliases": ["MRA"], "variants": [{"role": "game", "label": "MRA", "exts": [".mra"], "delay": 0, "type": "", "index": 0}]}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


def _safe_name(value, fallback):
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._")
    return value or fallback


def _image_from_bytes(data):
    image = Image.open(io.BytesIO(data))
    image.load()
    return image.convert("RGBA") if image.mode in ("RGBA", "LA", "P") else image.convert("RGB")


def _process_image(data, kind):
    image = _image_from_bytes(data)
    if kind == "wallpaper":
        target_w, target_h = 1280, 720
        scale = max(target_w / image.width, target_h / image.height)
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        image = image.resize(size, Image.Resampling.LANCZOS)
        left = max(0, (image.width - target_w) // 2)
        top = max(0, (image.height - target_h) // 2)
        image = image.crop((left, top, left + target_w, top + target_h))
    elif kind == "artwork":
        if image.width > 500 or image.height > 500:
            image.thumbnail((500, 500), Image.Resampling.LANCZOS)
    elif kind == "logo":
        if image.width > 600 or image.height > 200:
            image.thumbnail((600, 200), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _read_url(url, max_bytes=32 * 1024 * 1024):
    req = urllib.request.Request(url, headers={"User-Agent": "MiSTer Companion"})
    with urllib.request.urlopen(req, timeout=20) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Downloaded file is too large.")
    return data


def _sftp_mkdirs(sftp, path):
    current = ""
    for part in path.strip("/").split("/"):
        current += "/" + part
        try:
            sftp.stat(current)
        except Exception:
            sftp.mkdir(current)


def _sftp_exists(sftp, path):
    try:
        sftp.stat(path)
        return True
    except Exception:
        return False


def _sftp_remove_tree(sftp, path):
    try:
        entries = sftp.listdir_attr(path)
    except Exception:
        try:
            sftp.remove(path)
        except Exception:
            pass
        return
    import stat
    for entry in entries:
        child = posixpath.join(path, entry.filename)
        if stat.S_ISDIR(entry.st_mode):
            _sftp_remove_tree(sftp, child)
        else:
            sftp.remove(child)
    sftp.rmdir(path)




class TransferOutputDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Transferring Collection to MiSTer")
        self.resize(560, 320)
        self.setModal(True)
        layout = QVBoxLayout(self)
        label = QLabel("Transferring collection files to MiSTer...")
        layout.addWidget(label)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)

    def write(self, text):
        self.output.append(str(text))
        bar = self.output.verticalScrollBar()
        bar.setValue(bar.maximum())
        QApplication.processEvents()

class RemoteGameBrowserDialog(QDialog):
    def __init__(self, connection, extensions=None, parent=None, roots=None):
        super().__init__(parent)
        self.connection = connection
        self.extensions = {e.lower() for e in (extensions or [])}
        self.selected_path = ""
        self.current_path = ""
        self.roots = list(roots or ONLINE_GAME_ROOTS)
        self.setWindowTitle("Select Game on MiSTer")
        self.resize(760, 560)
        layout = QVBoxLayout(self)
        roots = QHBoxLayout()
        for label, path in self.roots:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, p=path: self.load_path(p))
            roots.addWidget(button)
        roots.addStretch(1)
        layout.addLayout(roots)
        self.path_label = QLabel("")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.path_label)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search games and folders...")
        self.search.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self.open_item)
        layout.addWidget(self.list, 1)
        row = QHBoxLayout()
        up = QPushButton("Up")
        up.clicked.connect(self.go_up)
        row.addWidget(up)
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        select = QPushButton("Select")
        select.clicked.connect(self.select_current)
        row.addWidget(cancel)
        row.addWidget(select)
        layout.addLayout(row)
        for _, root in self.roots:
            if self._exists(root):
                self.load_path(root)
                break

    def _exists(self, path):
        sftp = self.connection.client.open_sftp()
        try:
            return _sftp_exists(sftp, path)
        finally:
            sftp.close()

    def load_path(self, path):
        sftp = self.connection.client.open_sftp()
        try:
            import stat
            if not _sftp_exists(sftp, path):
                QMessageBox.information(self, "Location Unavailable", f"{path} is not available.")
                return
            entries = []
            for attr in sftp.listdir_attr(path):
                if attr.filename in {".", ".."}:
                    continue
                is_dir = stat.S_ISDIR(attr.st_mode)
                if not is_dir and self.extensions and Path(attr.filename).suffix.lower() not in self.extensions:
                    continue
                entries.append((not is_dir, attr.filename.lower(), attr.filename, is_dir))
            entries.sort()
        finally:
            sftp.close()
        self.current_path = path
        self.path_label.setText(path)
        self.list.clear()
        for _, _, name, is_dir in entries:
            item = QListWidgetItem(("📁 " if is_dir else "") + name)
            item.setData(Qt.ItemDataRole.UserRole, {"name": name, "is_dir": is_dir})
            self.list.addItem(item)
        self._apply_filter(self.search.text())


    def _apply_filter(self, text):
        needle = (text or "").strip().lower()
        for index in range(self.list.count()):
            item = self.list.item(index)
            data = item.data(Qt.ItemDataRole.UserRole) or {}
            name = str(data.get("name", "")).lower()
            item.setHidden(bool(needle) and needle not in name)

    def open_item(self, item):
        data = item.data(Qt.ItemDataRole.UserRole) or {}
        path = posixpath.join(self.current_path, data.get("name", ""))
        if data.get("is_dir"):
            self.load_path(path)
        else:
            self.selected_path = path
            self.accept()

    def go_up(self):
        roots = [p for _, p in self.roots]
        if self.current_path in roots:
            return
        parent = posixpath.dirname(self.current_path.rstrip("/"))
        allowed = next((r for r in roots if parent == r or parent.startswith(r + "/")), None)
        if allowed:
            self.load_path(parent)

    def select_current(self):
        item = self.list.currentItem()
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole) or {}
        if data.get("is_dir"):
            self.open_item(item)
            return
        self.selected_path = posixpath.join(self.current_path, data.get("name", ""))
        self.accept()


class LocalGameBrowserDialog(QDialog):
    def __init__(self, sd_root, extensions=None, parent=None, arcade=False):
        super().__init__(parent)
        self.sd_root = Path(sd_root).expanduser().resolve()
        self.extensions = {e.lower() for e in (extensions or [])}
        self.selected_path = ""
        self.root = self.sd_root / ("_Arcade" if arcade else "games")
        self.root.mkdir(parents=True, exist_ok=True)
        self.current_path = self.root
        self.setWindowTitle("Select Game on SD Card")
        self.resize(760, 560)
        layout = QVBoxLayout(self)
        self.path_label = QLabel("")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.path_label)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search games and folders...")
        self.search.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self.open_item)
        layout.addWidget(self.list, 1)
        row = QHBoxLayout()
        up = QPushButton("Up")
        up.clicked.connect(self.go_up)
        row.addWidget(up)
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        select = QPushButton("Select")
        select.clicked.connect(self.select_current)
        row.addWidget(cancel)
        row.addWidget(select)
        layout.addLayout(row)
        self.load_path(self.root)

    def load_path(self, path):
        path = Path(path).resolve()
        try:
            path.relative_to(self.root)
        except ValueError:
            return
        self.current_path = path
        self.path_label.setText(str(path))
        self.list.clear()
        entries = []
        try:
            for child in path.iterdir():
                is_dir = child.is_dir()
                if not is_dir and self.extensions and child.suffix.lower() not in self.extensions:
                    continue
                entries.append((not is_dir, child.name.lower(), child.name, is_dir))
        except OSError as exc:
            QMessageBox.warning(self, "Select Game", str(exc))
            return
        entries.sort()
        for _, _, name, is_dir in entries:
            item = QListWidgetItem(("📁 " if is_dir else "") + name)
            item.setData(Qt.ItemDataRole.UserRole, {"name": name, "is_dir": is_dir})
            self.list.addItem(item)
        self._apply_filter(self.search.text())

    def _apply_filter(self, text):
        needle = (text or "").strip().lower()
        for index in range(self.list.count()):
            item = self.list.item(index)
            data = item.data(Qt.ItemDataRole.UserRole) or {}
            name = str(data.get("name", "")).lower()
            item.setHidden(bool(needle) and needle not in name)

    def open_item(self, item):
        data = item.data(Qt.ItemDataRole.UserRole) or {}
        path = self.current_path / data.get("name", "")
        if data.get("is_dir"):
            self.load_path(path)
        else:
            self.selected_path = "/media/fat/" + str(path.relative_to(self.sd_root)).replace("\\", "/")
            self.accept()

    def go_up(self):
        if self.current_path == self.root:
            return
        self.load_path(self.current_path.parent)

    def select_current(self):
        item = self.list.currentItem()
        if not item or item.isHidden():
            return
        self.open_item(item)


class AssetField(QWidget):
    def __init__(self, label, kind, required=False, wav_only=False, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.required = required
        self.wav_only = wav_only
        self.source = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.name = QLineEdit()
        self.name.setReadOnly(True)
        self.name.setPlaceholderText("Required" if required else "Optional")
        layout.addWidget(self.name, 1)
        upload = QPushButton("Upload")
        upload.clicked.connect(self.pick_file)
        url = QPushButton("URL")
        url.clicked.connect(self.pick_url)
        remove = QPushButton("Remove")
        remove.clicked.connect(self.clear)
        layout.addWidget(upload)
        layout.addWidget(url)
        layout.addWidget(remove)

    def set_existing(self, filename):
        if filename:
            self.source = {"type": "existing", "name": filename}
            self.name.setText(filename)

    def clear(self):
        self.source = None
        self.name.clear()

    def pick_file(self):
        filt = "WAV Audio (*.wav)" if self.wav_only else "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        path, _ = QFileDialog.getOpenFileName(self, "Select File", "", filt)
        if not path:
            return
        if self.wav_only and Path(path).suffix.lower() != ".wav":
            QMessageBox.warning(self, "Unsupported Audio", "Collection Launcher music must be a WAV file.")
            return
        self.source = {"type": "file", "path": path, "name": Path(path).name}
        self.name.setText(Path(path).name)

    def pick_url(self):
        url, ok = QInputDialog.getText(self, "Use URL", "URL:")
        if not ok or not url.strip():
            return
        url = url.strip()
        name = "music.wav" if self.wav_only else (Path(url.split("?", 1)[0]).name or "image.png")
        self.source = {"type": "url", "url": url, "name": name}
        self.name.setText(name)

    def materialize(self, existing_reader=None):
        if not self.source:
            return None
        st = self.source.get("type")
        if st == "existing":
            return {"existing": True, "name": self.source["name"]}
        if st == "file":
            data = Path(self.source["path"]).read_bytes()
        else:
            data = _read_url(self.source["url"])
        if self.wav_only:
            if not data.startswith(b"RIFF") or data[8:12] != b"WAVE":
                raise ValueError("Music must be a valid WAV file.")
            return {"data": data, "name": "music.wav"}
        data = _process_image(data, self.kind)
        suffix_name = {"wallpaper": "wallpaper.png", "logo": "logo.png", "artwork": "artwork.png"}[self.kind]
        return {"data": data, "name": suffix_name}


class GameEntryDialog(QDialog):
    def __init__(self, manager, entry=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.original = deepcopy(entry or {})
        self.result_entry = None
        self.file_rows = []
        self.setWindowTitle("Edit Game" if entry else "Add Game")
        self.resize(760, 650)
        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.form = QFormLayout(body)
        self.label_edit = QLineEdit((entry or {}).get("label", ""))
        self.form.addRow("Label", self.label_edit)
        self.system = QComboBox()
        systems = sorted(SYSTEM_PRESETS.keys(), key=str.lower)
        self.system.addItems(systems)
        self.system.currentTextChanged.connect(self.rebuild_files)
        self.form.addRow("System", self.system)
        self.files_box = QWidget()
        self.files_layout = QVBoxLayout(self.files_box)
        self.files_layout.setContentsMargins(0, 0, 0, 0)
        self.form.addRow("Game File(s)", self.files_box)
        self.ram = QComboBox()
        self.ram.addItems(["none", "1MB", "4MB"])
        self.form.addRow("Saturn RAM", self.ram)
        self.ram_label = self.form.labelForField(self.ram)
        self.artwork = AssetField("Artwork", "artwork", required=True)
        self.form.addRow("Artwork", self.artwork)
        self.art_note = QLabel("Automatically scaled to fit within 500×500 while preserving aspect ratio.")
        self.art_note.setWordWrap(True)
        self.form.addRow("", self.art_note)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save Game")
        save.clicked.connect(self.save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)
        launch = (entry or {}).get("launch") or {}
        sys_name = launch.get("system") or "PSX"
        idx = self.system.findText(sys_name)
        if idx >= 0:
            self.system.setCurrentIndex(idx)
        self.ram.setCurrentText(launch.get("ram") or "none")
        self.artwork.set_existing((entry or {}).get("artwork"))
        self.rebuild_files(self.system.currentText(), launch)

    def _clear_rows(self):
        while self.files_layout.count():
            item = self.files_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.file_rows = []

    def rebuild_files(self, system, launch=None):
        self._clear_rows()
        launch = launch or {}
        preset = SYSTEM_PRESETS.get(system, {})
        variants = preset.get("variants", [])
        existing_files = launch.get("files") or []
        if launch.get("path"):
            existing_files = [{"role": variants[0]["role"] if variants else "game", "path": launch["path"]}]
        show_saturn_ram = system == "Saturn"
        self.ram.setVisible(show_saturn_ram)
        if self.ram_label:
            self.ram_label.setVisible(show_saturn_ram)
        # One row per distinct role. This mirrors Collection Launcher's accepted role set.
        seen = set()
        for variant in variants:
            role = variant["role"]
            if role in seen:
                continue
            seen.add(role)
            row = QWidget()
            hl = QHBoxLayout(row); hl.setContentsMargins(0,0,0,0)
            label = QLabel(variant.get("label") or role)
            label.setMinimumWidth(105)
            edit = QLineEdit()
            match = next((f for f in existing_files if (f.get("role") or role) == role), None)
            if match: edit.setText(match.get("path", ""))
            browse = QPushButton("Browse")
            exts = set()
            for v in variants:
                if v["role"] == role: exts.update(v.get("exts", []))
            browse.clicked.connect(lambda checked=False, e=edit, x=exts: self.browse_game(e, x))
            hl.addWidget(label); hl.addWidget(edit,1); hl.addWidget(browse)
            self.files_layout.addWidget(row)
            self.file_rows.append((role, edit, exts))
        if not variants:
            note = QLabel("No MGL preset is defined for this system in Collection Launcher.")
            self.files_layout.addWidget(note)

    def browse_game(self, edit, exts):
        path = self.manager.browse_game(exts, arcade=self.system.currentText() == "Arcade")
        if path:
            edit.setText(path)

    def save(self):
        label = self.label_edit.text().strip()
        if not label:
            QMessageBox.warning(self, "Missing Label", "Enter a game label.")
            return
        selected = [(role, edit.text().strip()) for role, edit, _ in self.file_rows if edit.text().strip()]
        if not selected:
            QMessageBox.warning(self, "Missing Game", "Select at least one game file.")
            return
        if not self.artwork.source:
            QMessageBox.warning(self, "Missing Artwork", "Select artwork for this game.")
            return
        system = self.system.currentText()
        # Keep single-file launches compact; multi-device systems use files.
        launch = {"system": system}
        if len(selected) == 1:
            launch["path"] = selected[0][1]
        else:
            launch["files"] = [{"role": role, "path": path} for role, path in selected]
        if system == "Saturn" and self.ram.currentText() != "none":
            launch["ram"] = self.ram.currentText()
        result = deepcopy(self.original)
        result.update({"label": label, "launch": launch})
        result["_artwork_source"] = self.artwork.source
        if self.artwork.source.get("type") == "existing":
            result["artwork"] = self.artwork.source["name"]
        self.result_entry = result
        self.accept()


class CollectionEditorDialog(QDialog):
    def __init__(self, manager, folder_name=None, data=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.folder_name = folder_name
        self.original = deepcopy(data or {})
        self.entries = deepcopy((data or {}).get("entries") or [])
        self.saved_folder = None
        self.setWindowTitle("Edit Collection" if data else "Add Collection")
        self.resize(900, 760)
        root = QVBoxLayout(self)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        body = QWidget(); body_layout = QVBoxLayout(body)
        form = QFormLayout()
        self.title = QLineEdit((data or {}).get("title", ""))
        self.cid = QLineEdit((data or {}).get("id", ""))
        form.addRow("Title", self.title); form.addRow("ID", self.cid)
        self.wallpaper = AssetField("Wallpaper", "wallpaper", required=True)
        self.logo = AssetField("Logo", "logo")
        self.music = AssetField("Music", "music", wav_only=True)
        self.wallpaper.set_existing((data or {}).get("wallpaper"))
        self.logo.set_existing((data or {}).get("logo"))
        self.music.set_existing((data or {}).get("music"))
        form.addRow("Wallpaper", self.wallpaper)
        form.addRow("", QLabel("Automatically resized/cropped to 1280×720."))
        form.addRow("Logo", self.logo)
        form.addRow("", QLabel("Maximum 600×200; aspect ratio preserved."))
        form.addRow("Music", self.music)
        form.addRow("", QLabel("WAV only."))
        body_layout.addLayout(form)
        body_layout.addWidget(QLabel("Games"))
        self.games = QListWidget(); self.games.setMinimumHeight(260)
        self.games.itemDoubleClicked.connect(lambda _: self.edit_game())
        body_layout.addWidget(self.games)
        grow = QHBoxLayout()
        add = QPushButton("+ Add Game"); add.clicked.connect(self.add_game)
        edit = QPushButton("Edit Game"); edit.clicked.connect(self.edit_game)
        remove = QPushButton("Remove Game"); remove.clicked.connect(self.remove_game)
        up = QPushButton("Move Up"); up.clicked.connect(lambda: self.move_game(-1))
        down = QPushButton("Move Down"); down.clicked.connect(lambda: self.move_game(1))
        for b in (add, edit, remove, up, down): grow.addWidget(b)
        grow.addStretch(1)
        body_layout.addLayout(grow)
        scroll.setWidget(body); root.addWidget(scroll,1)
        bottom = QHBoxLayout(); bottom.addStretch(1)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        save = QPushButton("Save Collection"); save.clicked.connect(self.save)
        bottom.addWidget(cancel); bottom.addWidget(save); root.addLayout(bottom)
        self.refresh_games()

    def refresh_games(self):
        self.games.clear()
        for entry in self.entries:
            launch = entry.get("launch") or {}
            item = QListWidgetItem(f"{entry.get('label','')}  —  {launch.get('system','')}")
            self.games.addItem(item)

    def add_game(self):
        dlg = GameEntryDialog(self.manager, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_entry:
            self.entries.append(dlg.result_entry); self.refresh_games()

    def edit_game(self):
        row = self.games.currentRow()
        if row < 0: return
        dlg = GameEntryDialog(self.manager, self.entries[row], self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_entry:
            self.entries[row] = dlg.result_entry; self.refresh_games(); self.games.setCurrentRow(row)

    def remove_game(self):
        row = self.games.currentRow()
        if row >= 0:
            self.entries.pop(row); self.refresh_games()

    def move_game(self, delta):
        row = self.games.currentRow(); target = row + delta
        if row < 0 or target < 0 or target >= len(self.entries): return
        self.entries[row], self.entries[target] = self.entries[target], self.entries[row]
        self.refresh_games(); self.games.setCurrentRow(target)

    def save(self):
        title = self.title.text().strip(); cid = self.cid.text().strip()
        if not title or not cid:
            QMessageBox.warning(self, "Missing Details", "Collection title and ID are required."); return
        if not self.wallpaper.source:
            QMessageBox.warning(self, "Missing Wallpaper", "A wallpaper is required."); return
        if not self.entries:
            QMessageBox.warning(self, "Missing Games", "Add at least one game."); return
        folder = self.folder_name or _safe_name(cid, "Collection")
        try:
            self.manager.save_collection(folder, self.original, title, cid, self.wallpaper, self.logo, self.music, self.entries)
        except Exception as exc:
            QMessageBox.critical(self, "Save Collection", str(exc)); return
        self.saved_folder = folder
        self.accept()


class CollectionLauncherManagerDialog(QDialog):
    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.connection = getattr(main_window, "connection", None)
        self.offline = bool(hasattr(main_window, "is_offline_mode") and main_window.is_offline_mode())
        self.sd_root = main_window.get_offline_sd_root() if self.offline and hasattr(main_window, "get_offline_sd_root") else ""
        self.collections = []
        self.setWindowTitle("Collection Launcher - Manage Collections")
        self.resize(920, 720); self.setMinimumSize(760, 520)
        root = QVBoxLayout(self)
        title = QLabel("Collections"); f = title.font(); f.setBold(True); f.setPointSize(f.pointSize()+2); title.setFont(f)
        root.addWidget(title)
        self.list = QListWidget(); self.list.itemDoubleClicked.connect(lambda _: self.edit_collection())
        root.addWidget(self.list,1)
        row = QHBoxLayout()
        add = QPushButton("+ Add Collection"); add.clicked.connect(self.add_collection)
        edit = QPushButton("Edit"); edit.clicked.connect(self.edit_collection)
        delete = QPushButton("Delete"); delete.clicked.connect(self.delete_collection)
        row.addWidget(add); row.addWidget(edit); row.addWidget(delete); row.addStretch(1)
        close = QPushButton("Close"); close.clicked.connect(self.accept); row.addWidget(close)
        root.addLayout(row)
        self.refresh()

    def _offline_root(self):
        if not self.sd_root: raise RuntimeError("No Offline SD card is selected.")
        return Path(self.sd_root).expanduser().resolve() / COLLECTIONS_REL

    def refresh(self):
        try: self.collections = self.load_collections()
        except Exception as exc:
            QMessageBox.critical(self, "Collection Launcher", str(exc)); self.collections = []
        self.list.clear()
        for folder, data in self.collections:
            item = QListWidgetItem(f"{data.get('title') or data.get('id') or folder}\nID: {data.get('id') or folder}    •    {len(data.get('entries') or [])} games")
            item.setData(Qt.ItemDataRole.UserRole, folder); self.list.addItem(item)

    def load_collections(self):
        out=[]
        if self.offline:
            root=self._offline_root(); root.mkdir(parents=True,exist_ok=True)
            for folder in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p:p.name.lower()):
                fp=folder/'collection.json'
                if fp.exists():
                    try: out.append((folder.name,json.loads(fp.read_text(encoding='utf-8'))))
                    except Exception: pass
        else:
            if not self.connection: raise RuntimeError("Not connected to MiSTer.")
            sftp=self.connection.client.open_sftp()
            try:
                _sftp_mkdirs(sftp,COLLECTIONS_REMOTE)
                for name in sorted(sftp.listdir(COLLECTIONS_REMOTE), key=str.lower):
                    fp=posixpath.join(COLLECTIONS_REMOTE,name,'collection.json')
                    try:
                        with sftp.open(fp,'r') as f:
                            raw=f.read()
                        if isinstance(raw,bytes): raw=raw.decode('utf-8')
                        out.append((name,json.loads(raw)))
                    except Exception: pass
            finally: sftp.close()
        return out

    def add_collection(self):
        dlg=CollectionEditorDialog(self,parent=self)
        if dlg.exec()==QDialog.DialogCode.Accepted: self.refresh()

    def edit_collection(self):
        item=self.list.currentItem()
        if not item: return
        folder=item.data(Qt.ItemDataRole.UserRole)
        data=next((d for f,d in self.collections if f==folder),None)
        if data is None:return
        dlg=CollectionEditorDialog(self,folder,data,self)
        if dlg.exec()==QDialog.DialogCode.Accepted:self.refresh()

    def delete_collection(self):
        item=self.list.currentItem()
        if not item:return
        folder=item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self,"Delete Collection",f"Delete collection '{folder}' and its uploaded assets?") != QMessageBox.StandardButton.Yes:return
        try:
            if self.offline: shutil.rmtree(self._offline_root()/folder)
            else:
                sftp=self.connection.client.open_sftp()
                try:_sftp_remove_tree(sftp,posixpath.join(COLLECTIONS_REMOTE,folder))
                finally:sftp.close()
        except Exception as exc: QMessageBox.critical(self,"Delete Collection",str(exc));return
        self.refresh()

    def browse_game(self, extensions, arcade=False):
        if self.offline:
            dlg=LocalGameBrowserDialog(self.sd_root,extensions,self,arcade=arcade)
            return dlg.selected_path if dlg.exec()==QDialog.DialogCode.Accepted else ''
        dlg=RemoteGameBrowserDialog(self.connection,extensions,self,roots=ONLINE_ARCADE_ROOTS if arcade else ONLINE_GAME_ROOTS)
        return dlg.selected_path if dlg.exec()==QDialog.DialogCode.Accepted else ''

    def _existing_bytes(self, folder, relname):
        if not relname:return None
        if self.offline:
            p=self._offline_root()/folder/relname
            return p.read_bytes() if p.exists() else None
        sftp=self.connection.client.open_sftp()
        try:
            with sftp.open(posixpath.join(COLLECTIONS_REMOTE,folder,relname),'rb') as f:return f.read()
        finally:sftp.close()

    def save_collection(self, folder, original, title, cid, wallpaper_field, logo_field, music_field, entries):
        folder = folder or _safe_name(cid, 'Collection')
        data=deepcopy(original or {})
        data['id']=cid; data['title']=title
        assets=[]
        def asset(field,kind,target,required=False):
            mat=field.materialize()
            if not mat:
                if required: raise ValueError(f"{kind.title()} is required.")
                data.pop(kind,None); return ''
            if mat.get('existing'): return mat['name']
            assets.append((target,mat['data'])); return target
        data['wallpaper']=asset(wallpaper_field,'wallpaper','wallpaper.png',True)
        logo=asset(logo_field,'logo','logo.png')
        if logo:data['logo']=logo
        else:data.pop('logo',None)
        music=asset(music_field,'music','music.wav')
        if music:data['music']=music
        else:data.pop('music',None)
        clean_entries=[]
        for index,entry in enumerate(entries,1):
            e=deepcopy(entry); source=e.pop('_artwork_source',None)
            if source and source.get('type')!='existing':
                if source['type']=='file': raw=Path(source['path']).read_bytes()
                else: raw=_read_url(source['url'])
                processed=_process_image(raw,'artwork')
                name=f"artwork/game_{index:02d}.png"; assets.append((name,processed));e['artwork']=name
            elif source and source.get('type')=='existing': e['artwork']=source['name']
            if not e.get('artwork'): raise ValueError(f"Artwork is required for game {index}.")
            clean_entries.append(e)
        data['entries']=clean_entries
        raw_json=(json.dumps(data,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
        if self.offline:
            root=self._offline_root()/folder; (root/'artwork').mkdir(parents=True,exist_ok=True)
            for rel,blob in assets:
                p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(blob)
            (root/'collection.json').write_bytes(raw_json)
        else:
            transfer = TransferOutputDialog(self)
            transfer.show()
            QApplication.processEvents()
            sftp = None
            try:
                transfer.write("Connecting to MiSTer...")
                sftp=self.connection.client.open_sftp()
                root=posixpath.join(COLLECTIONS_REMOTE,folder)
                transfer.write(f"Preparing {root}")
                _sftp_mkdirs(sftp,root);_sftp_mkdirs(sftp,posixpath.join(root,'artwork'))
                for rel,blob in assets:
                    target=posixpath.join(root,rel);_sftp_mkdirs(sftp,posixpath.dirname(target))
                    transfer.write(f"Uploading {rel} ({len(blob):,} bytes)...")
                    with sftp.open(target,'wb') as f:f.write(blob)
                    transfer.write(f"Finished {rel}")
                transfer.write(f"Uploading collection.json ({len(raw_json):,} bytes)...")
                with sftp.open(posixpath.join(root,'collection.json'),'wb') as f:f.write(raw_json)
                transfer.write("Transfer complete.")
            except Exception as exc:
                transfer.write(f"ERROR: {exc}")
                transfer.setWindowTitle("Collection Transfer Failed")
                transfer.setModal(False)
                raise
            finally:
                if sftp is not None:
                    sftp.close()
            transfer.accept()
