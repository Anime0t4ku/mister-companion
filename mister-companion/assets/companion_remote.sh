#!/bin/sh

TITLE="MiSTer Companion Remote by Anime0t4ku"
SCRIPT_VERSION="4.0.3"
SCRIPT_PATH="/media/fat/Scripts/companion_remote.sh"

BASE="/media/fat/Scripts/.config/companion_remote"
DAEMON="$BASE/companion_remote_daemon"
CONFIG="$BASE/config.ini"
LOG="$BASE/companion_remote.log"
PID="$BASE/companion_remote.pid"

STARTUP="/media/fat/linux/user-startup.sh"
STARTUP_DIR="/media/fat/linux"

PORT="9191"
HOST="0.0.0.0"
WS_PATH="/remote/v1"

UNATTENDED=0
COMMAND=""

mkdir -p "$BASE"

print_line() {
    printf '%s\n' "$1"
}

has_cmd() {
    command -v "$1" >/dev/null 2>&1
}

dialog_box() {
    clear
    dialog --clear --title "$TITLE" "$@"
    RESULT=$?
    clear
    sleep 0.3
    return $RESULT
}

show_message() {
    dialog_box --msgbox "$1" 14 82
}

log_line() {
    mkdir -p "$BASE" 2>/dev/null
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$LOG"
}

ensure_base() {
    mkdir -p "$BASE" 2>/dev/null
}

write_default_config() {
    ensure_base

    if [ ! -f "$CONFIG" ]; then
        cat > "$CONFIG" <<EOF
[server]
host=$HOST
port=$PORT
path=$WS_PATH

[input]
virtual_keyboard=true
virtual_controller=true
EOF
    fi
}

create_daemon_file() {
    ensure_base

    cat > "$DAEMON" <<'PYEOF'
#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import os
import signal
import shlex
import shutil
import socket
import struct
import subprocess
import sys
import time
import threading
import fcntl
import glob
import select
import termios
import urllib.parse
import re
from html import escape as xml_escape

DAEMON_VERSION = "__COMPANION_REMOTE_VERSION__"

UINPUT_PATH = "/dev/uinput"

UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_ABSBIT = 0x40045567

EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03

SYN_REPORT = 0
BUS_USB = 0x03


BTN_SOUTH = 304
BTN_EAST = 305
BTN_WEST = 307
BTN_NORTH = 308
BTN_TL = 310
BTN_TR = 311
BTN_SELECT = 314
BTN_START = 315
BTN_MODE = 316

KEY_CODES = {
    "KEY_ESC": 1,
    "KEY_1": 2,
    "KEY_2": 3,
    "KEY_3": 4,
    "KEY_4": 5,
    "KEY_5": 6,
    "KEY_6": 7,
    "KEY_7": 8,
    "KEY_8": 9,
    "KEY_9": 10,
    "KEY_0": 11,
    "KEY_MINUS": 12,
    "KEY_EQUAL": 13,
    "KEY_BACKSPACE": 14,
    "KEY_TAB": 15,
    "KEY_Q": 16,
    "KEY_W": 17,
    "KEY_E": 18,
    "KEY_R": 19,
    "KEY_T": 20,
    "KEY_Y": 21,
    "KEY_U": 22,
    "KEY_I": 23,
    "KEY_O": 24,
    "KEY_P": 25,
    "KEY_LEFTBRACE": 26,
    "KEY_RIGHTBRACE": 27,
    "KEY_ENTER": 28,
    "KEY_LEFTCTRL": 29,
    "KEY_A": 30,
    "KEY_S": 31,
    "KEY_D": 32,
    "KEY_F": 33,
    "KEY_G": 34,
    "KEY_H": 35,
    "KEY_J": 36,
    "KEY_K": 37,
    "KEY_L": 38,
    "KEY_SEMICOLON": 39,
    "KEY_APOSTROPHE": 40,
    "KEY_GRAVE": 41,
    "KEY_LEFTSHIFT": 42,
    "KEY_BACKSLASH": 43,
    "KEY_Z": 44,
    "KEY_X": 45,
    "KEY_C": 46,
    "KEY_V": 47,
    "KEY_B": 48,
    "KEY_N": 49,
    "KEY_M": 50,
    "KEY_COMMA": 51,
    "KEY_DOT": 52,
    "KEY_SLASH": 53,
    "KEY_RIGHTSHIFT": 54,
    "KEY_KPASTERISK": 55,
    "KEY_LEFTALT": 56,
    "KEY_SPACE": 57,
    "KEY_CAPSLOCK": 58,
    "KEY_F1": 59,
    "KEY_F2": 60,
    "KEY_F3": 61,
    "KEY_F4": 62,
    "KEY_F5": 63,
    "KEY_F6": 64,
    "KEY_F7": 65,
    "KEY_F8": 66,
    "KEY_F9": 67,
    "KEY_F10": 68,
    "KEY_NUMLOCK": 69,
    "KEY_SCROLLLOCK": 70,
    "KEY_KP7": 71,
    "KEY_KP8": 72,
    "KEY_KP9": 73,
    "KEY_KPMINUS": 74,
    "KEY_KP4": 75,
    "KEY_KP5": 76,
    "KEY_KP6": 77,
    "KEY_KPPLUS": 78,
    "KEY_KP1": 79,
    "KEY_KP2": 80,
    "KEY_KP3": 81,
    "KEY_KP0": 82,
    "KEY_KPDOT": 83,
    "KEY_F11": 87,
    "KEY_F12": 88,
    "KEY_RIGHTCTRL": 97,
    "KEY_KPSLASH": 98,
    "KEY_RIGHTALT": 100,
    "KEY_HOME": 102,
    "KEY_UP": 103,
    "KEY_PAGEUP": 104,
    "KEY_LEFT": 105,
    "KEY_RIGHT": 106,
    "KEY_END": 107,
    "KEY_DOWN": 108,
    "KEY_PAGEDOWN": 109,
    "KEY_INSERT": 110,
    "KEY_DELETE": 111,
    "KEY_PAUSE": 119,
    "KEY_LEFTMETA": 125,
    "KEY_RIGHTMETA": 126,
}

CONTROLLER_BUTTONS = {
    "a": BTN_SOUTH,
    "b": BTN_EAST,
    "x": BTN_WEST,
    "y": BTN_NORTH,
    "l": BTN_TL,
    "r": BTN_TR,
    "lb": BTN_TL,
    "rb": BTN_TR,
    "select": BTN_SELECT,
    "start": BTN_START,
    "mode": BTN_MODE,
    "home": BTN_MODE,
}

running = True

LOGO_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAUAAAABQCAYAAABoMayFAAAACXBIWXMAAAsTAAALEwEAmpwYAAAX50lEQVR4nO2dX2wcRZ7Hv9Xjf3FMMuMkOIkB2Q5GF3GwgA92V1oOBF7Q7aJk98HZg717grWlBQEroTMSf24f0F4s7Wn34diLEwmxf3g4IsgC5rS6WEgHL+iIb489InA2cUhEDgy2Zxz/mX+eqXto17inXT1dVV3d047rI7XkGXfXn57qb/+qflW/IpRSGAwGw2bEqncBDAaDoV4YATQYDJsWI4AGg2HTEqkA/uTJJx8ghJwnhCxHmS8ArOZ7Pup8DQZDfGmIMrMtra2LhJCuejheCCFdkWdqMBhiTaQC+PHHH19VL6+z8XYbDAY3kXSBOzs7L1qWRb/x9a+/mUmnQSmFZVnUsqxQVenUBx/ssiyLEkJoem4OmXQahBBqWRb9yZNPHgwzb4PBEH8isQDLpVITpRRbt27F9mQSQDQWWVtb2wLLJ5lKVb6nlOLc1FQy9AIYDIZYE5oFODAw0EEIoYQQevbs2Y5MOo3W1lYQQkAIQSadRnpuDuycd95553pdebM0jx07ls2k01heWqrkSylFJp3Gd7/znZcJIbS9vX1GV74Gg2FjEZoFuGPHjhL7m1IKSikIUBEhdmD1O90QQmBZ1lrejjyc31mWVaqRjEGOQQCjEudPAdgXMD9m2g87/q7F067Px1fLYdiEaBfABx54YOzs2bPXtLe3zzGB6+joQKlUwvDdD2H5xXfRsn0ndvb2VgQKlOKFF174+0cfffTA9PT0nrm5ud0qee/fv/+PCwsLV7E0333vPVzf24vFpSUs/ct/VqzAHTt2YHh4GOVSCRT4v66urk8aGxuLd9xxxwOvvPLKBa03ZI0eAOc0pPNXACYUrjsFoC9g3uMAvh0wDScqwjPgOFQ4zPmcBtDu+n6Yc25cmIDdDgwB0S6AmUym5cyZM1/r7e3FwuXLsCwLxWIRmUwGhVIRl7NLAIC5uTkAwNLiIlZWVkAIeX5ycjLQ2ODk5OQtlFIU8nlks1nk83nMzc2BUoqF3NrUw7m5OSQSCczPz6OpqemWCxdszdu/f3+YA5Mi1okIfZAXwD4EF7960w9bkMKoh67fJirS9S7AlYI2AfzewYO7Z2dncfWuXbPd3d3o3LsXMzMzsCwLpZLdy1zO57CUzyJhJSrXpdNpFAoFNDU3o7u7G8VCAX995527ZYVwenqadnd3I5fL4YvpaawUi1heXhO9pXy26vzM/DxmZ2dBCMF1112HRCKBmZmZ5J3f+lZh3/XXZ15++eVcgNvBQ9dD1qNwTb+mvP0sNtk6ilqAUVhjPaguj8p9jgrTZdeFczwuyNHT3X2WEEKzS0s0k07TqXPnKADKHBJ+x+uvv04z6TRdKRaFr3EeAGgmnabZ5WWpfNva2ujy0hKdz2ToLbfcQgkh9O677rpb131xHINUD6cU8p7TlPeoTz7DmtNTSVOVPle+oxHlq8Jhqr99bspDmwVYLpctStesNva38zs/Ieb9LQtzdajkyz6XSiX9Xhm9XWC3tVILp6MgKLotD7/0+hDdOFwPqocW4twtNl1gTQQWwFXrC5RSLC0uIl8oAAB27tyJxYUF4XRKpRIopVhcXJS6zsnKygpy+bz09YXVMr/37rsghODRxx57hxCCXbt2zX755Zc7lQoTLgMARgTPHQ6zIC5GIF4uEaJ0Qri7vHEWQIMmtFiAbIrJyspK5TtKadVnGVSvC3o9G6sEtafINDQ0FAIVpBqdY0qiAtivOd8oLY8U1McupwAcXT14ZU7BtowZAzACuCmJdC3wJkfnA8W8un7e4CitP92oit9RAEM+56RR/QLhvUxUppmchHy5h2CXOWxYW0ihdrtw3ps0oimbm37Y7Zs3t3MfNA7FGAGMDt0WRT9qC2A/9Hl/GX4N7xzkLM5a89lU75d7onPcCdOjOwzb0pX5TVKoHnoYhT1ZnB0iyM55ZS8tNuaru916oiSAw8PDN+ZzuUQun7f+7oc/BCEExYLO3mJ9+cY3v4lyuYzmlpb/euLxx2/OFwqJI0eO/DFgsrqnVfh1g0WtvzTq192r9fBvloH+MOqpe9oQm3g+AVuoVCbii+Txagjp1oSoeFy7urr+cPHixfsppZjPZAJ5bePM9mTSuZwuqGd4DmJCcxziqxy8VoWIvoGPY82rHCQ/hqwFWKu7moJ9z2QR6QKHhcpqm3boE8Ee2CIS9qT3Q6htDcr+dlMQbzdau8AmJH40pCBuZYl2MwDvroKo9Sc7vqPbWvGzAFXGnwZRB0tiFRVLWtc97YOe5Y4ivIpqJ5Ib2TrJvDS19qSMAEaD6IMxBXu9rSg8S9Ht4dSVlwiyAuD3oIwInMNjALY1GtlYkiK6LJkUbFGKcihjFBt/eaURwIgQfWtNwX7gRYWpD+sbvYj4AWrWlZ8Y6RbAKagHX+iB7ZWViU4TFN31F2UUcpZRGrazqB322gECe3hDtk3UI1iEsQA3IDICCMhZZm4rR0QAVbuXurvAIukxT7Fq3oOwrUHV6DEy1EMAZSPjTMAeR3Nb18zBIeNFZ9NVNixGAKNBpgsMyI0DOhug6MTn44iHl1W0C8hEULXLzpwDUXcT/dDxG8haYYd88h2BXNecJ75BrTTmyCKcQ+u8RCOA0SD60LGGOQXxqQZOC1DUEnAKrC5BCFtYWHc4yDy/AdjeyTCsQZWHPqgAyq70OQoxcZN50ei0AKdgv+iimhxuBDAiVB4OUSuQjQOKOj8mUN3AZcXZCxUBVHECjMB+SII4EF5FPIKd6hBAGXQ7vQB9Y3LsBRfGHENPYrkShG2ctLqLW81zGxsb0bp1KwBgPpMJuWTKyI4BAvLjgKICpPpmjUOXmcHGsUYh7vRxMwz75aErwnU9psDICmAY04N4bVtFFIdQhziHsbMA29raKqHr29rafM8/c+ZM5fwYI9og3IPSog2iD2LdujTC6f4C8o1eh6AOwRYw1bT6YXuKdRD12GIK8XBA6Pgd3b2SyNAmgDqDFDp3cPM7rESiIn668g8B1W6maDd4AGLWgDs6Sj0dArosynHY1qCM48gJC7UflKjHAOPizNFhtdVF/ABNXWBKKR5/4gnosMFatmyp/D00NLQWosqDy5cvV/5+4oknNJQAeOSRR3DzzTdrSQtyD4a7MYmOh4jmEWRgOYwxQF2kYXs3ZXelYwzDfgjr9iBuYLyWYspQtxD/2sYA33jjDSwoBjL14uVf/1r4XEIIfvu732nJ9+DBg1rSWSXIIPE49AUrGMf6hiaTbpwFkHEU9gN5SuHafgQTwKicQEGI6zjRxhdARmdnp2c3MpvNIp2u/RxRStHZ2QkAuHTpEgghSKVSsKzq3nomk0GpVEJrayuSySQIIbh06ZJv+a655hqUy2Xu/7766isUi0XfNCRRcYAw2KoQHdM2eNafTtGKgwACtgCOQD4WYtBlc1HXn60aist9dxLW5lja0S6Af56crITFd/Paa6/hkR/9yDeN0x99BABIpuz7+E8/+xk6r7mm8n/LsjA4OIhLly7hwIED+Ndf/Qqtra1obmnxTfvixYtcbzEhBHfdfTc+/PBD3zQkCTrNZALBBXAK6mNkYREnr7IO6iFEU5BzhAS1ckWJoyhzidQLXC6XPR0NOhwQtdII0cHhR1AB1NFgvcb+dK6r1OUF7oPtmR1WSJOVQ+WFEdQKqcdEaNmXWlRzHzeMBSglgGwryQsXLtyvktlDDz2EXDbLFaKxsTHkslnkc2rb8S4tLVXS5u30ll1eRi6bRcanC85j1SvNttKckbw8SBcYsC3AIJND6xXWXJUJrHlmzwGgsB0bw+CHSGcMrP5fNiahM98g1EMAZX/XqEJmxXlP5Sqku8BB5tsVi0UUi0VuV7VQKCCnKH6sXLlcztPKy+VygeYLOqbayHp6dDSGcag32lrrfmXe1H5vaZ2N3h0g0znZOQwrRsdLoh7dPrZ/h8x4JxNB5vU+jtq/rTtttoFUe41rNkwXWEgADxw48G8AcGZyksLhSSoUi0rdysWFBUx+8knVd62trZ7n/+KXv0SrY3oMAMzM8A2xYrGI06dPo7GhumoqwscrJ6X0P9j9ePPNN38gkExQCxAIZp1EZf2FKYBhoxp3kCET8FY3I+DvaucH2zNG5YXi1/W+sgRwbGzsEAD89je/0ZJpqVTC1VdfLXz+5OSk8Lnlchmde/eqFGsdHuUcHBsbY8LvJ4C6HgzV6TDjqC2e9VwJUosox4SOIvhexqr3UYcjiM2BPBmgHLL4vZCv3C6wF7feeisopZiensbK6uTlnTvl9xRPJBKYnp6u+u5re3qxtam62/zfl84gt5JHPp/HzMwMSqUSOjo6lMr+1VdfwbIs3HTTTdi2bRu2rq4t1oBMt7XWw6A6HSaqN7XuBh+Vh3gEenaRU62/rnqycGFR7AcC1HbMbRjrD9C4Mfobv/89AODW227Dp59+it7eXpz64APPOXdebNmyBb033FBJFwB+8d3H0dPeWZXfPccew7m5Szhx4gROnDgBSqmSg6OpqamS3//+6U+49tprpdOogU5hkJ0OIzKutVkFcAK28OmaEhIHi4eFktK9I5ybNKLrVYSOkADKjPMtLy1V1vO2tLRIC2CioWFdfglYaEysFdW59tdJi8A8QDeNjY2Vv/2W3TEk7ofOB0P2YRXp1sk01lp12SgCeBS2VVzvvVDCZAR2PQchvyewCH73Lg4vA2F8t8UkhNDL8/MAICRmbMXG7OwsunvU7sXbb79d9fnIkSN46623qr577bXXqgSvpaUF9957r3ReW7duxezMDAqFgrBYszpu275dx3aZBm/6sH6FhmjkmwmsDQHULdpITHB6cgcg3k12B1ANOlYaO4QsQBkrjp3LhFXW++o1YdmZDqUUpVKp6rzyqtUpCyEE5XJZqY4xD8F1JRB0DqTBZsTj702PkAWoMrZGKUU+n/c9Z8/evSCE4B9/+lP85Y03AljflV1ZWcHKykrVd83NzesEKJfLoSGRwPe+/30QQvDoj3+MZ5991resKl1nAEi1t6NcLhsVNBg2KKFFhGZjgLVwiq8FbyFqaGhAQ4N/UVtaWtDU1FT53NzcrCxuBoPhyqfuIfH/9gf2VLpEIoEvp6dBKUXH7t1V56TTaRRdARZ2XX11lQVICMH0F1/AsiwcGhiAZVnoUhyDNBgMm4PQusCisPxffPFFPPf886CUYmxsrOqc0dHRqu8opXj11VerVo80NzfjvvvuA6UUuWwW2Ww29DE60wU2GDY2QhYgW4a2nM1qL8DWVRFjkWIAW8yc8BwjiUSi6rzm5ua161taYBGCUrnsOw6pArsfdYouYzAYNOErgJRSQgihAJQmGvukjabVMTrH8rJ1lttLL72Ep556qvI5kUjgwQcfxGeffbYuPef1Dz/8MP755z/XWmYAlTKbKTAGw8ZGyAIMuytJCEGhUMB8JlPZFc7JSrGIxcXFymfLsuxt4l1TY+YzmYpVSAhBcvv20MprrD+DYeNTdyeIm3w+j9EjR6oEZnp6Gh+dPl35TCnFM888UyWAy8vLkZbTsKkYgNw2pYYNQuwEsFgs4tChQ1Xf/cPwMI4dO1b5TCnFpc8+0xm0oN6wKMY9UFtKdBy1oz57pc0e6loxA50cxvpVBLo2tB7F+vK5Ny3n5a8CWxkiujrk8Oq5QxJ58Mo6IpEnow/r1/byfm9efqKbvutqI1HXOTBCArhjx45pALAsa124Fdm1vm7a2tqQSCTWbXrkpLGxEdu2bat89luz29raisbGxqp1vqpwyvU/O3bs2AM9O2z1wP6hg+75wWtgImmzZWaHsbaGtFYj5y1NG4X4g+YFW7fqBy9/FfphLw87DlvUatWZracdhH2PZDar5y3j+zbkVrekOOnwfm+Ve6O7jURd58D4ToOpOtkOCV/5zMbdgoyHiS6Zc+dR63zVZXhutieT6wSQUvoppbQ7UMI2OqN2PI3qJU6qabPYcl6N7ST4D9khqG+6lIIdxp4XUMD9A3rlH4QJ2A+o10PtDLF/FOJWoFdZ05AThP7VtJy4f2+v/Go9AGG0kajrHBipPUEsyyoTQspUowdANEw9O0/k/CCh72ukWSaElC3LCmby2owivJBFQdJOwW54ItaYk8NQj4hSa5+PKOB1txjujZkGEbwLzu5xFHH7vIi6jcShzlykxgBLpVICAPbt2/fv58+f/5twihQ/KKUol8sJTckdhnfjOQ61AACsWyaadgpr4z68RjkK+60tatU5u4gy9EB+/143st1v1v11wuvepjjnAfY9DtrlZ4Ig2zXUQb3aSD3r7ImSE6RUKkW6neYVBO/hA+xG9DSCORNU0h5ZvY7ngBjFWih+EdiYmkwdRiXO9UJ2bIjVyW0B9aG67IPgW6ZsL42gY1JMEPYhugjY9W4j9ahzTYyQRQuv8R2FPaYS1JOqmvY47EjC7rdyCvLdHJlu1QD0j+eJwrNAnA+3l/XHULVa3b8DE4SohgDq0UbqXeeaGAGMDp6HbAJyUyvCSpsNbLvfyrIPuqioyYqlbnhdOhHrj8GsQFl495htBB+2INSrjdSzzr4YAYwO3gOjy6ulI+0prJ9nxZuO4MbduEW6tbxQ7TonGbOxRd5xEnzxHXdcKyLOKgLu5XGOQhDq1UbqWWdfjABGB2+Cs+rUkbDS9usa8nA/RH6ODZ7A8B6sILA8eIeXELAH1Kub6BboPsh7y4H6CUI920hsRVBJAEulUiKKtbAsEGqto9YEah1orGeYwQl1pc0bmPZrnLyJsbWmtvAsJx1bU6rCHADAmjfbzQj41pLqWKCfIIRBPdsIUJ86+yKlHmwe3MSpUzcsXL6MhcuXQw0K0HbVVb7H4JCOITQ+85kMWD0JIXR1HuRFxeTC9HrVM+001guY1xhfP9avOhiHPktYlqdhj1ExeILGvKNHsd768RJMEZgguOmDHu+4mzi0v6jr7Ius+UQAkHK5fF2pVBLeRjII7gnQvCNMXPUkAFQrzes6BF0CpzttXvdQZGyO10Uc5KTHa+RhbNLDNpLnHWwz9HZX3v1YL2buvZV5lmqQidxeTohB6BeEercRZzmiqrMvouGwTgLAn8+coZZlkTD32WhtbcVf7N8PAEgmk3u6u7trKtydd965dFtf3/zi4iLOTE6GVq5PPv4YjY2NyOZy17P7QSmVmRDLa4CD0GP96EibN6WBCYkIQ1jflTkMe/oEsH5VBWCLSxhrPL0sjVrwrD/n2CCwJqJOEVCdBM5gAut++Nlvocs6jkMbYURVZ19EBbAfAHbt2hVuaWAHHzh//jwAoFwuf+F3/vvvv99y/vz50OPz7V7bp2RFMR7gOOw3pVME2MTUoFaQjrRHsd6SkWmIPHHow9oEaS+BiQO8aS1u648xwjl3GP6BJGpRSxB0LR+LQxtxEkWdfYmNF7itrQ3bk0kkGhqwe/fuT/fs2XNe5LpEIkE6OjouNDY1LW5PJrE9mYxzsFJeF4p5J4N6wlTT7oFtubm7Q2nIC5RXF5FXhqArX3QiYv0xeGG0ZCeN8/AKtKBTDOLQRpxEUeeaxCYe4MjICJ597jm2/4dwtJXbb789+/nnn3cBgGVZlFKKfC6HbAj7l2iAxTRzPyzDsBvXcah1CVm8Npm02fytAfAbv4pATXDKkAL/wdEe200R3uTtKdR+sIdgR4lxEtQKBLytIl3EoY24CbvONRESwCgsqhhbbVVosDCfhv2Gc7/lnJN3VdJkg/s60j4KdYEagfcD4zwnFmtBwfdW+1k1zCvsFvrDCL6y5yjU5xiKEIc2wksrzDp7ItQFppQSSilJplJIplJIh7hNZhwhhIDVnRCSZ/dDMbk0bMdAGBaQjrSHEOwh9rOe/P4fJV4rUkTuH68OvPRUGBIsgwpxaCNeaUbeK5AeAySEIEwvcBxxBVj9XFOyQ9ATBEFX2uOwo3ToaIS1uoL1nPTshmftiD7YXkIZNLyXsxxhCkK92wiP6EWQ7bkrcyQSiYsAqM7j1KlTe1XKwjt0l82+TXrK5nH0U0oPU0pPUjWGFdKeW/1umFLaI1hOXvm8zh3knHuyxvnDAmnL5O93yJaPd6SofR/d9Ggs6ygnHd7vHSQ/XW0k6joHPqRC4jO6urr+cPHixfulL6zB+Ph47z333HNWR1ru0P1BWb1ZZg9gg+EKIzbTYAwGgyFqlCxAg8FguBIwFqDBYNi0GAE0GAyblv8HfV9KGMi93IsAAAAASUVORK5CYII=")
HOME_HTML = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover"><meta name="theme-color" content="#120f1c"><title>MiSTer Companion Remote</title><style>\n:root{--bg:#120f1c;--panel:#1b1628;--panel2:#2b2340;--text:#f2ecff;--muted:#b5a9c9;--accent:#8b5cf6;--accent2:#a78bfa;--ok:#39d98a;--danger:#d95768;--border:#3a2f55;--shadow:0 18px 55px rgba(0,0,0,.42)}\n*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html,body{margin:0;min-height:100%;background:radial-gradient(circle at top,#261c3d 0,#120f1c 48%,#0b0911 100%);color:var(--text);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}body{min-height:100dvh}.shell{width:min(1220px,100%);margin:0 auto;padding:16px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 16px;background:rgba(27,22,40,.94);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow);position:relative;z-index:20}.brand{display:flex;align-items:center;gap:12px;min-width:0}.brand img{width:74px;height:auto}.brand-copy{min-width:0}.brand h1{font-size:1rem;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.brand p{margin:3px 0 0;color:var(--muted);font-size:.78rem}.status{display:flex;align-items:center;gap:8px;font-weight:800;font-size:.84rem;white-space:nowrap}.dot{width:10px;height:10px;border-radius:50%;background:#81768f;box-shadow:0 0 0 4px rgba(129,118,143,.12)}.status.connected .dot{background:var(--ok);box-shadow:0 0 0 4px rgba(57,217,138,.13)}.status.disconnected .dot{background:var(--danger);box-shadow:0 0 0 4px rgba(217,87,104,.14)}.nav{display:flex;gap:8px;margin:12px 0}.nav a{flex:1;text-align:center;text-decoration:none;color:var(--text);background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:10px;font-weight:800}.nav a.active,.nav a:hover{background:var(--accent);border-color:var(--accent2)}.card{background:rgba(27,22,40,.96);border:1px solid var(--border);border-radius:22px;box-shadow:var(--shadow)}button{font:inherit;color:inherit}.btn{border:1px solid #5b4a7a;background:linear-gradient(180deg,#352a4f,#241d35);border-radius:14px;min-height:50px;font-weight:900;box-shadow:inset 0 1px rgba(255,255,255,.06),0 5px 14px rgba(0,0,0,.25);cursor:pointer;user-select:none;touch-action:none;transition:transform .06s,background .1s,border-color .1s}.btn.active,.btn:active{transform:translateY(2px) scale(.98);background:var(--accent);border-color:var(--accent2)}.danger{background:#48232d;border-color:#7a3848}.footer{text-align:center;color:var(--muted);font-size:.75rem;padding:14px}.rotate-tip{display:none;position:fixed;inset:0;background:rgba(11,9,17,.94);z-index:100;align-items:center;justify-content:center;padding:24px}.rotate-card{max-width:390px;text-align:center;background:var(--panel);border:1px solid var(--accent);border-radius:22px;padding:26px;box-shadow:var(--shadow)}.rotate-icon{font-size:3rem;margin-bottom:8px}.rotate-card h2{margin:6px 0}.rotate-card p{color:var(--muted);line-height:1.45}.rotate-card .btn{width:100%;margin-top:12px}.toast{position:fixed;left:50%;bottom:20px;transform:translate(-50%,20px);opacity:0;pointer-events:none;background:#2b2340;border:1px solid #5b4a7a;border-radius:12px;padding:11px 16px;z-index:120;transition:.2s;box-shadow:var(--shadow)}.toast.show{opacity:1;transform:translate(-50%,0)}\n@media(max-width:700px){.map-item{grid-template-columns:minmax(80px,.8fr) minmax(0,1.2fr)}.map-listen{grid-column:2;width:100%}.shell{padding:7px}.topbar{padding:8px 10px;border-radius:14px}.brand img{width:46px}.brand p{display:none}.brand h1{font-size:.82rem}.status{font-size:.7rem}.nav{margin:7px 0;gap:5px}.nav a{padding:7px 4px;font-size:.74rem;border-radius:9px}.footer{display:none}}\n@media(max-width:700px) and (orientation:portrait){.rotate-tip.show{display:flex}}\n\n.home{padding:32px}.hero{text-align:center;max-width:720px;margin:auto}.hero img{width:min(220px,55vw)}.hero h2{font-size:clamp(1.6rem,5vw,2.7rem);margin:8px 0}.hero p{color:var(--muted);line-height:1.55}.choices{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-top:25px}.choice{display:block;text-decoration:none;color:var(--text);padding:24px;border-radius:18px;background:var(--panel2);border:1px solid var(--border);transition:.15s}.choice:hover{transform:translateY(-2px);border-color:var(--accent2)}.choice strong{display:block;font-size:1.18rem;margin-bottom:7px}.choice span{color:var(--muted)}.power{margin-top:20px;padding-top:20px;border-top:1px solid var(--border)}.power h3{margin:0 0 6px}.power p{color:var(--muted);margin:0 0 14px}.power-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.power .soft{background:linear-gradient(180deg,#47366b,#302348);border-color:var(--accent)}.modal{display:none;position:fixed;inset:0;background:rgba(11,9,17,.78);z-index:110;align-items:center;justify-content:center;padding:20px}.modal.show{display:flex}.modal-card{width:min(420px,100%);background:var(--panel);border:1px solid var(--accent);border-radius:20px;padding:22px;box-shadow:var(--shadow)}.modal-card h3{margin-top:0}.modal-card p{color:var(--muted);line-height:1.45}.modal-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:18px}@media(max-width:650px){.home{padding:18px 13px}.choices,.power-grid{grid-template-columns:1fr}.choice{padding:18px}}\n</style></head><body><div class="shell"><header class="topbar"><div class="brand"><img src="/assets/logo.png" alt="MiSTer Companion"><div class="brand-copy"><h1>MiSTer Companion Remote</h1><p>Browser remote v4.0.3</p></div></div><div class="status disconnected"><i class="dot"></i><span>Disconnected</span></div></header><nav class="nav"><a href="/" class="active">Home</a><a href="/controller" class="">Controller</a><a href="/keyboard" class="">Keyboard</a><a href="/games" class="">Games</a><a href="/scripts" class="">Scripts</a><a href="/bluebridge">BlueBridge</a></nav><main class="card home"><div class="hero"><img src="/assets/logo.png" alt="MiSTer Companion logo"><p>Choose the dedicated controller or keyboard interface. Everything runs locally on your MiSTer.</p></div><div class="choices"><a class="choice" href="/controller"><strong>Virtual Controller</strong><span>Responsive gamepad controls optimized for landscape use.</span></a><a class="choice" href="/keyboard"><strong>Virtual Keyboard</strong><span>A full keyboard that scales to the available screen.</span></a><a class="choice" href="/games"><strong>Game Launcher</strong><span>Browse installed systems and launch games directly from this MiSTer.</span></a><a class="choice" href="/scripts"><strong>Scripts</strong><span>Browse and launch MiSTer scripts with an interactive console.</span></a><div class="choice" style="cursor:default"><strong>Screenshot</strong><span>Ask MiSTer to capture and save the current screen.</span><button class="btn" style="width:100%;margin-top:14px" onclick="captureScreenshot()">Capture screenshot</button></div></div><section class="screenshot-panel" style="display:none;margin-top:20px;padding-top:20px;border-top:1px solid var(--border)"><img class="screenshot-image" alt="MiSTer screenshot" style="display:block;max-width:100%;max-height:60vh;margin:auto;border-radius:14px;border:1px solid var(--border)"></section><section class="power"><h3>Power actions</h3><div class="power-grid"><button class="btn soft" onclick="askPower(\'soft_reboot\',\'Reload Menu\',\'Reload menu.rbf and return to the MiSTer menu?\')">Reload Menu</button><button class="btn danger" onclick="askPower(\'cold_reboot\',\'Reboot\',\'Fully restart the MiSTer? The web remote will disconnect temporarily.\')">Reboot</button></div></section></main><div class="footer">MiSTer Companion Remote by Anime0t4ku</div></div><div class="modal"><div class="modal-card"><h3 class="modal-title"></h3><p class="modal-text"></p><div class="modal-actions"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn danger confirm-power">Confirm</button></div></div></div><div class="toast"></div><script>\nconst state={ws:null,connected:false,held:new Set(),reconnect:null,heartbeat:null,connecting:false};\nfunction wsURL(){const p=location.protocol===\'https:\'?\'wss\':\'ws\';return `${p}://${location.host}/remote/v1`}\nfunction setStatus(ok){state.connected=ok;document.querySelectorAll(\'.status\').forEach(el=>{el.classList.toggle(\'connected\',ok);el.classList.toggle(\'disconnected\',!ok);el.querySelector(\'span\').textContent=ok?\'Connected\':\'Disconnected\'})}\nfunction connect(){clearTimeout(state.reconnect);if(state.connecting||state.ws?.readyState===WebSocket.OPEN||state.ws?.readyState===WebSocket.CONNECTING)return;state.connecting=true;try{state.ws=new WebSocket(wsURL())}catch(e){state.connecting=false;scheduleReconnect();return}state.ws.onopen=()=>{state.connecting=false;setStatus(true);clearInterval(state.heartbeat);state.heartbeat=setInterval(()=>{if(state.ws?.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:"ping"}))},25000)};state.ws.onclose=()=>{state.connecting=false;clearInterval(state.heartbeat);state.heartbeat=null;setStatus(false);releaseVisuals();scheduleReconnect()};state.ws.onerror=()=>setStatus(false)}\nfunction scheduleReconnect(){clearTimeout(state.reconnect);state.reconnect=setTimeout(connect,1500)}\nfunction send(obj){if(state.ws&&state.ws.readyState===WebSocket.OPEN){state.ws.send(JSON.stringify(obj));return true}showToast(\'Remote is disconnected\');return false}\nfunction ctl(name,action){return send({type:\'controller\',control:[\'up\',\'down\',\'left\',\'right\'].includes(name)?\'dpad\':\'button\',name,action})}\nfunction key(name,action){return send({type:\'keyboard\',key:name,action})}\nfunction systemCommand(command){return send({type:\'system\',command})}\nfunction releaseAll(){if(state.ws&&state.ws.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:\'system\',command:\'release_all\'}));releaseVisuals()}\nfunction releaseVisuals(){state.held.clear();document.querySelectorAll(\'.active\').forEach(el=>el.classList.remove(\'active\'))}\nfunction bindHold(selector,callback){document.querySelectorAll(selector).forEach(el=>{const id=el.dataset.name||el.dataset.key;const down=e=>{e.preventDefault();try{el.setPointerCapture(e.pointerId)}catch(_){}if(state.held.has(el))return;state.held.add(el);el.classList.add(\'active\');callback(id,\'down\')};const up=e=>{e.preventDefault();if(!state.held.has(el))return;state.held.delete(el);el.classList.remove(\'active\');callback(id,\'up\')};el.addEventListener(\'pointerdown\',down);[\'pointerup\',\'pointercancel\',\'lostpointercapture\'].forEach(ev=>el.addEventListener(ev,up));el.addEventListener(\'contextmenu\',e=>e.preventDefault())})}\nfunction showToast(message){const t=document.querySelector(\'.toast\');if(!t)return;t.textContent=message;t.classList.add(\'show\');clearTimeout(t._timer);t._timer=setTimeout(()=>t.classList.remove(\'show\'),2400)}\nfunction setupRotateTip(){const tip=document.querySelector(\'.rotate-tip\');if(!tip)return;const update=()=>{const portrait=matchMedia(\'(orientation: portrait)\').matches&&innerWidth<=700;tip.classList.toggle(\'show\',portrait&&!sessionStorage.getItem(\'remotePortraitDismissed\'))};document.querySelector(\'.rotate-dismiss\')?.addEventListener(\'click\',()=>{sessionStorage.setItem(\'remotePortraitDismissed\',\'1\');tip.classList.remove(\'show\')});addEventListener(\'resize\',update);screen.orientation?.addEventListener?.(\'change\',update);update()}\nwindow.addEventListener(\'blur\',releaseAll);document.addEventListener(\'visibilitychange\',()=>{if(document.hidden)releaseAll()});window.addEventListener(\'beforeunload\',releaseAll);document.addEventListener(\'DOMContentLoaded\',()=>{connect();setupRotateTip()});\n\nfunction captureScreenshot(){const panel=document.querySelector(\'.screenshot-panel\'),img=document.querySelector(\'.screenshot-image\');showToast(\'Capturing screenshot…\');fetch(\'/api/screenshot?fresh=1&_t=\'+Date.now()).then(async r=>{if(!r.ok)throw new Error(await r.text()||\'Screenshot failed\');return r.blob()}).then(blob=>{if(img._url)URL.revokeObjectURL(img._url);img._url=URL.createObjectURL(blob);img.src=img._url;panel.style.display=\'block\';showToast(\'Screenshot captured\')}).catch(e=>showToast(e.message||\'Screenshot failed\'))}\nlet pendingPower=\'\';function askPower(command,title,message){pendingPower=command;document.querySelector(\'.modal-title\').textContent=title;document.querySelector(\'.modal-text\').textContent=message;document.querySelector(\'.modal\').classList.add(\'show\')}function closeModal(){document.querySelector(\'.modal\').classList.remove(\'show\');pendingPower=\'\'}document.querySelector(\'.confirm-power\').addEventListener(\'click\',()=>{const cmd=pendingPower;closeModal();if(systemCommand(cmd))showToast(cmd===\'soft_reboot\'?\'Reloading menu…\':\'Reboot requested…\')});document.querySelector(\'.modal\').addEventListener(\'click\',e=>{if(e.target.classList.contains(\'modal\'))closeModal()});\n</script></body></html>'.encode("utf-8")
CONTROLLER_HTML = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover"><meta name="theme-color" content="#120f1c"><title>Controller · MiSTer Companion Remote</title><style>\n:root{--bg:#120f1c;--panel:#1b1628;--panel2:#2b2340;--text:#f2ecff;--muted:#b5a9c9;--accent:#8b5cf6;--accent2:#a78bfa;--ok:#39d98a;--danger:#d95768;--border:#3a2f55;--shadow:0 18px 55px rgba(0,0,0,.42)}\n*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html,body{margin:0;min-height:100%;background:radial-gradient(circle at top,#261c3d 0,#120f1c 48%,#0b0911 100%);color:var(--text);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}body{min-height:100dvh}.shell{width:min(1220px,100%);margin:0 auto;padding:16px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 16px;background:rgba(27,22,40,.94);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow);position:relative;z-index:20}.brand{display:flex;align-items:center;gap:12px;min-width:0}.brand img{width:74px;height:auto}.brand-copy{min-width:0}.brand h1{font-size:1rem;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.brand p{margin:3px 0 0;color:var(--muted);font-size:.78rem}.status{display:flex;align-items:center;gap:8px;font-weight:800;font-size:.84rem;white-space:nowrap}.dot{width:10px;height:10px;border-radius:50%;background:#81768f;box-shadow:0 0 0 4px rgba(129,118,143,.12)}.status.connected .dot{background:var(--ok);box-shadow:0 0 0 4px rgba(57,217,138,.13)}.status.disconnected .dot{background:var(--danger);box-shadow:0 0 0 4px rgba(217,87,104,.14)}.nav{display:flex;gap:8px;margin:12px 0}.nav a{flex:1;text-align:center;text-decoration:none;color:var(--text);background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:10px;font-weight:800}.nav a.active,.nav a:hover{background:var(--accent);border-color:var(--accent2)}.card{background:rgba(27,22,40,.96);border:1px solid var(--border);border-radius:22px;box-shadow:var(--shadow)}button{font:inherit;color:inherit}.btn{border:1px solid #5b4a7a;background:linear-gradient(180deg,#352a4f,#241d35);border-radius:14px;min-height:50px;font-weight:900;box-shadow:inset 0 1px rgba(255,255,255,.06),0 5px 14px rgba(0,0,0,.25);cursor:pointer;user-select:none;touch-action:none;transition:transform .06s,background .1s,border-color .1s}.btn.active,.btn:active{transform:translateY(2px) scale(.98);background:var(--accent);border-color:var(--accent2)}.danger{background:#48232d;border-color:#7a3848}.footer{text-align:center;color:var(--muted);font-size:.75rem;padding:14px}.rotate-tip{display:none;position:fixed;inset:0;background:rgba(11,9,17,.94);z-index:100;align-items:center;justify-content:center;padding:24px}.rotate-card{max-width:390px;text-align:center;background:var(--panel);border:1px solid var(--accent);border-radius:22px;padding:26px;box-shadow:var(--shadow)}.rotate-icon{font-size:3rem;margin-bottom:8px}.rotate-card h2{margin:6px 0}.rotate-card p{color:var(--muted);line-height:1.45}.rotate-card .btn{width:100%;margin-top:12px}.toast{position:fixed;left:50%;bottom:20px;transform:translate(-50%,20px);opacity:0;pointer-events:none;background:#2b2340;border:1px solid #5b4a7a;border-radius:12px;padding:11px 16px;z-index:120;transition:.2s;box-shadow:var(--shadow)}.toast.show{opacity:1;transform:translate(-50%,0)}\n@media(max-width:700px){.map-item{grid-template-columns:minmax(80px,.8fr) minmax(0,1.2fr)}.map-listen{grid-column:2;width:100%}.shell{padding:7px}.topbar{padding:8px 10px;border-radius:14px}.brand img{width:46px}.brand p{display:none}.brand h1{font-size:.82rem}.status{font-size:.7rem}.nav{margin:7px 0;gap:5px}.nav a{padding:7px 4px;font-size:.74rem;border-radius:9px}.footer{display:none}}\n@media(max-width:700px) and (orientation:portrait){.rotate-tip.show{display:flex}}\n\n.stage{position:relative;width:100%;overflow:hidden}.scale-box{position:absolute;left:50%;top:0;width:1000px;height:560px;transform-origin:top center;transform:translateX(-50%) scale(var(--ui-scale,1))}.controller-card{width:1000px;height:560px;padding:18px}.shoulders{display:grid;grid-template-columns:1fr 1fr;gap:20px}.shoulders .btn{height:58px}.controller-wrap{display:grid;grid-template-columns:330px 1fr 330px;gap:24px;align-items:center;height:390px}.section-label{text-align:center;color:var(--muted);font-weight:800;font-size:.75rem;letter-spacing:.08em;text-transform:uppercase;margin-bottom:10px}.dpad{display:grid;grid-template-columns:repeat(3,88px);grid-template-rows:repeat(3,88px);justify-content:center}.dpad .btn{border-radius:18px;font-size:1.55rem}.up{grid-column:2}.left{grid-column:1;grid-row:2}.right{grid-column:3;grid-row:2}.down{grid-column:2;grid-row:3}.dpad-center{grid-column:2;grid-row:2;background:#100c18;border:1px solid #302442;border-radius:18px}.center-buttons{display:grid;gap:10px}.center-buttons .btn{height:54px}.face{position:relative;width:280px;height:280px;margin:auto}.face .btn{position:absolute;width:88px;height:88px;border-radius:50%;font-size:1.25rem}.face .x{top:0;left:96px}.face .y{top:96px;left:0}.face .a{top:96px;right:0}.face .b{bottom:0;left:96px}.release{width:100%;height:48px}@media(max-width:700px){.stage{margin-top:0}.scale-box{top:0}}\n</style></head><body><div class="shell"><header class="topbar"><div class="brand"><img src="/assets/logo.png" alt="MiSTer Companion"><div class="brand-copy"><h1>MiSTer Companion Remote</h1><p>Browser remote v4.0.3</p></div></div><div class="status disconnected"><i class="dot"></i><span>Disconnected</span></div></header><nav class="nav"><a href="/" class="">Home</a><a href="/controller" class="active">Controller</a><a href="/keyboard" class="">Keyboard</a><a href="/games" class="">Games</a><a href="/scripts" class="">Scripts</a><a href="/bluebridge">BlueBridge</a></nav><div class="stage"><div class="scale-box"><main class="card controller-card"><div class="shoulders"><button class="btn control" data-name="l">L</button><button class="btn control" data-name="r">R</button></div><div class="controller-wrap"><section><div class="section-label">D-Pad</div><div class="dpad"><button class="btn control up" data-name="up">▲</button><button class="btn control left" data-name="left">◀</button><div class="dpad-center"></div><button class="btn control right" data-name="right">▶</button><button class="btn control down" data-name="down">▼</button></div></section><section><div class="section-label">System</div><div class="center-buttons"><button class="btn control" data-name="select">Select</button><button class="btn control" data-name="home">Home</button><button class="btn control" data-name="start">Start</button></div></section><section><div class="section-label">Buttons</div><div class="face"><button class="btn control x" data-name="x">X</button><button class="btn control y" data-name="y">Y</button><button class="btn control a" data-name="a">A</button><button class="btn control b" data-name="b">B</button></div></section></div><button class="btn danger release" onclick="releaseAll()">Release all inputs</button></main></div></div><div class="footer">MiSTer Companion Remote by Anime0t4ku</div></div><div class="rotate-tip"><div class="rotate-card"><div class="rotate-icon">↻</div><h2>Rotate your phone</h2><p>The remote is designed to use the available screen best in landscape orientation.</p><button class="btn rotate-dismiss">Continue in portrait</button></div></div><div class="toast"></div><script>\nconst state={ws:null,connected:false,held:new Set(),reconnect:null,heartbeat:null,connecting:false};\nfunction wsURL(){const p=location.protocol===\'https:\'?\'wss\':\'ws\';return `${p}://${location.host}/remote/v1`}\nfunction setStatus(ok){state.connected=ok;document.querySelectorAll(\'.status\').forEach(el=>{el.classList.toggle(\'connected\',ok);el.classList.toggle(\'disconnected\',!ok);el.querySelector(\'span\').textContent=ok?\'Connected\':\'Disconnected\'})}\nfunction connect(){clearTimeout(state.reconnect);if(state.connecting||state.ws?.readyState===WebSocket.OPEN||state.ws?.readyState===WebSocket.CONNECTING)return;state.connecting=true;try{state.ws=new WebSocket(wsURL())}catch(e){state.connecting=false;scheduleReconnect();return}state.ws.onopen=()=>{state.connecting=false;setStatus(true);clearInterval(state.heartbeat);state.heartbeat=setInterval(()=>{if(state.ws?.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:"ping"}))},25000)};state.ws.onclose=()=>{state.connecting=false;clearInterval(state.heartbeat);state.heartbeat=null;setStatus(false);releaseVisuals();scheduleReconnect()};state.ws.onerror=()=>setStatus(false)}\nfunction scheduleReconnect(){clearTimeout(state.reconnect);state.reconnect=setTimeout(connect,1500)}\nfunction send(obj){if(state.ws&&state.ws.readyState===WebSocket.OPEN){state.ws.send(JSON.stringify(obj));return true}showToast(\'Remote is disconnected\');return false}\nfunction ctl(name,action){return send({type:\'controller\',control:[\'up\',\'down\',\'left\',\'right\'].includes(name)?\'dpad\':\'button\',name,action})}\nfunction key(name,action){return send({type:\'keyboard\',key:name,action})}\nfunction systemCommand(command){return send({type:\'system\',command})}\nfunction releaseAll(){if(state.ws&&state.ws.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:\'system\',command:\'release_all\'}));releaseVisuals()}\nfunction releaseVisuals(){state.held.clear();document.querySelectorAll(\'.active\').forEach(el=>el.classList.remove(\'active\'))}\nfunction bindHold(selector,callback){document.querySelectorAll(selector).forEach(el=>{const id=el.dataset.name||el.dataset.key;const down=e=>{e.preventDefault();try{el.setPointerCapture(e.pointerId)}catch(_){}if(state.held.has(el))return;state.held.add(el);el.classList.add(\'active\');callback(id,\'down\')};const up=e=>{e.preventDefault();if(!state.held.has(el))return;state.held.delete(el);el.classList.remove(\'active\');callback(id,\'up\')};el.addEventListener(\'pointerdown\',down);[\'pointerup\',\'pointercancel\',\'lostpointercapture\'].forEach(ev=>el.addEventListener(ev,up));el.addEventListener(\'contextmenu\',e=>e.preventDefault())})}\nfunction showToast(message){const t=document.querySelector(\'.toast\');if(!t)return;t.textContent=message;t.classList.add(\'show\');clearTimeout(t._timer);t._timer=setTimeout(()=>t.classList.remove(\'show\'),2400)}\nfunction setupRotateTip(){const tip=document.querySelector(\'.rotate-tip\');if(!tip)return;const update=()=>{const portrait=matchMedia(\'(orientation: portrait)\').matches&&innerWidth<=700;tip.classList.toggle(\'show\',portrait&&!sessionStorage.getItem(\'remotePortraitDismissed\'))};document.querySelector(\'.rotate-dismiss\')?.addEventListener(\'click\',()=>{sessionStorage.setItem(\'remotePortraitDismissed\',\'1\');tip.classList.remove(\'show\')});addEventListener(\'resize\',update);screen.orientation?.addEventListener?.(\'change\',update);update()}\nwindow.addEventListener(\'blur\',releaseAll);document.addEventListener(\'visibilitychange\',()=>{if(document.hidden)releaseAll()});window.addEventListener(\'beforeunload\',releaseAll);document.addEventListener(\'DOMContentLoaded\',()=>{connect();setupRotateTip()});\n\nfunction fitUI(){const stage=document.querySelector(\'.stage\');if(!stage)return;const vv=window.visualViewport;const vh=vv?vv.height:innerHeight;const top=stage.getBoundingClientRect().top-(vv?vv.offsetTop:0);const aw=Math.max(240,stage.clientWidth);const ah=Math.max(180,vh-top-6);const scale=Math.min(aw/1000,ah/560,1.18);document.documentElement.style.setProperty(\'--ui-scale\',scale);stage.style.height=(560*scale)+\'px\'}document.addEventListener(\'DOMContentLoaded\',()=>{bindHold(\'.control\',ctl);fitUI()});addEventListener(\'resize\',fitUI);visualViewport?.addEventListener(\'resize\',fitUI);screen.orientation?.addEventListener?.(\'change\',()=>setTimeout(fitUI,80));\n</script></body></html>'.encode("utf-8")
KEYBOARD_HTML = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover"><meta name="theme-color" content="#120f1c"><title>Keyboard · MiSTer Companion Remote</title><style>\n:root{--bg:#120f1c;--panel:#1b1628;--panel2:#2b2340;--text:#f2ecff;--muted:#b5a9c9;--accent:#8b5cf6;--accent2:#a78bfa;--ok:#39d98a;--danger:#d95768;--border:#3a2f55;--shadow:0 18px 55px rgba(0,0,0,.42)}\n*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html,body{margin:0;min-height:100%;background:radial-gradient(circle at top,#261c3d 0,#120f1c 48%,#0b0911 100%);color:var(--text);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}body{min-height:100dvh}.shell{width:min(1220px,100%);margin:0 auto;padding:16px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 16px;background:rgba(27,22,40,.94);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow);position:relative;z-index:20}.brand{display:flex;align-items:center;gap:12px;min-width:0}.brand img{width:74px;height:auto}.brand-copy{min-width:0}.brand h1{font-size:1rem;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.brand p{margin:3px 0 0;color:var(--muted);font-size:.78rem}.status{display:flex;align-items:center;gap:8px;font-weight:800;font-size:.84rem;white-space:nowrap}.dot{width:10px;height:10px;border-radius:50%;background:#81768f;box-shadow:0 0 0 4px rgba(129,118,143,.12)}.status.connected .dot{background:var(--ok);box-shadow:0 0 0 4px rgba(57,217,138,.13)}.status.disconnected .dot{background:var(--danger);box-shadow:0 0 0 4px rgba(217,87,104,.14)}.nav{display:flex;gap:8px;margin:12px 0}.nav a{flex:1;text-align:center;text-decoration:none;color:var(--text);background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:10px;font-weight:800}.nav a.active,.nav a:hover{background:var(--accent);border-color:var(--accent2)}.card{background:rgba(27,22,40,.96);border:1px solid var(--border);border-radius:22px;box-shadow:var(--shadow)}button{font:inherit;color:inherit}.btn{border:1px solid #5b4a7a;background:linear-gradient(180deg,#352a4f,#241d35);border-radius:14px;min-height:50px;font-weight:900;box-shadow:inset 0 1px rgba(255,255,255,.06),0 5px 14px rgba(0,0,0,.25);cursor:pointer;user-select:none;touch-action:none;transition:transform .06s,background .1s,border-color .1s}.btn.active,.btn:active{transform:translateY(2px) scale(.98);background:var(--accent);border-color:var(--accent2)}.danger{background:#48232d;border-color:#7a3848}.footer{text-align:center;color:var(--muted);font-size:.75rem;padding:14px}.rotate-tip{display:none;position:fixed;inset:0;background:rgba(11,9,17,.94);z-index:100;align-items:center;justify-content:center;padding:24px}.rotate-card{max-width:390px;text-align:center;background:var(--panel);border:1px solid var(--accent);border-radius:22px;padding:26px;box-shadow:var(--shadow)}.rotate-icon{font-size:3rem;margin-bottom:8px}.rotate-card h2{margin:6px 0}.rotate-card p{color:var(--muted);line-height:1.45}.rotate-card .btn{width:100%;margin-top:12px}.toast{position:fixed;left:50%;bottom:20px;transform:translate(-50%,20px);opacity:0;pointer-events:none;background:#2b2340;border:1px solid #5b4a7a;border-radius:12px;padding:11px 16px;z-index:120;transition:.2s;box-shadow:var(--shadow)}.toast.show{opacity:1;transform:translate(-50%,0)}\n@media(max-width:700px){.map-item{grid-template-columns:minmax(80px,.8fr) minmax(0,1.2fr)}.map-listen{grid-column:2;width:100%}.shell{padding:7px}.topbar{padding:8px 10px;border-radius:14px}.brand img{width:46px}.brand p{display:none}.brand h1{font-size:.82rem}.status{font-size:.7rem}.nav{margin:7px 0;gap:5px}.nav a{padding:7px 4px;font-size:.74rem;border-radius:9px}.footer{display:none}}\n@media(max-width:700px) and (orientation:portrait){.rotate-tip.show{display:flex}}\n\n.stage{position:relative;width:100%;overflow:hidden}.scale-box{position:absolute;left:50%;top:0;width:1180px;height:520px;transform-origin:top center;transform:translateX(-50%) scale(var(--ui-scale,1))}.keyboard-card{width:1180px;height:520px;padding:14px}.keyboard-tools{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.keyboard-tools h2{margin:0;font-size:1.05rem}.keyboard-tools .btn{min-height:38px;padding:0 14px}.key-row{display:flex;gap:5px;margin-bottom:5px}.key{flex:var(--w,1);min-width:0;height:53px;border-radius:9px;font-size:.78rem;padding:0 3px}.bottom{display:grid;grid-template-columns:1fr 230px;gap:10px}.nav-cluster{display:grid;grid-template-columns:repeat(6,1fr);gap:5px}.nav-cluster .key{height:44px}.arrows{display:grid;grid-template-columns:repeat(3,1fr);grid-template-rows:repeat(2,44px);gap:5px}.arrows .key{height:44px}.au{grid-column:2}.al{grid-column:1;grid-row:2}.ad{grid-column:2;grid-row:2}.ar{grid-column:3;grid-row:2}\n</style></head><body><div class="shell"><header class="topbar"><div class="brand"><img src="/assets/logo.png" alt="MiSTer Companion"><div class="brand-copy"><h1>MiSTer Companion Remote</h1><p>Browser remote v4.0.3</p></div></div><div class="status disconnected"><i class="dot"></i><span>Disconnected</span></div></header><nav class="nav"><a href="/" class="">Home</a><a href="/controller" class="">Controller</a><a href="/keyboard" class="active">Keyboard</a><a href="/games" class="">Games</a><a href="/scripts" class="">Scripts</a><a href="/bluebridge">BlueBridge</a></nav><div class="stage"><div class="scale-box"><main class="card keyboard-card"><div class="keyboard-tools"><h2>Virtual Keyboard</h2><button class="btn danger" onclick="releaseAll()">Release all inputs</button></div><div class="key-row"><button class="btn key" style="--w:1" data-key="KEY_ESC">Esc</button><button class="btn key" style="--w:1" data-key="KEY_F1">F1</button><button class="btn key" style="--w:1" data-key="KEY_F2">F2</button><button class="btn key" style="--w:1" data-key="KEY_F3">F3</button><button class="btn key" style="--w:1" data-key="KEY_F4">F4</button><button class="btn key" style="--w:1" data-key="KEY_F5">F5</button><button class="btn key" style="--w:1" data-key="KEY_F6">F6</button><button class="btn key" style="--w:1" data-key="KEY_F7">F7</button><button class="btn key" style="--w:1" data-key="KEY_F8">F8</button><button class="btn key" style="--w:1" data-key="KEY_F9">F9</button><button class="btn key" style="--w:1" data-key="KEY_F10">F10</button><button class="btn key" style="--w:1" data-key="KEY_F11">F11</button><button class="btn key" style="--w:1" data-key="KEY_F12">F12</button></div><div class="key-row"><button class="btn key" style="--w:1" data-key="KEY_GRAVE">`</button><button class="btn key" style="--w:1" data-key="KEY_1">1</button><button class="btn key" style="--w:1" data-key="KEY_2">2</button><button class="btn key" style="--w:1" data-key="KEY_3">3</button><button class="btn key" style="--w:1" data-key="KEY_4">4</button><button class="btn key" style="--w:1" data-key="KEY_5">5</button><button class="btn key" style="--w:1" data-key="KEY_6">6</button><button class="btn key" style="--w:1" data-key="KEY_7">7</button><button class="btn key" style="--w:1" data-key="KEY_8">8</button><button class="btn key" style="--w:1" data-key="KEY_9">9</button><button class="btn key" style="--w:1" data-key="KEY_0">0</button><button class="btn key" style="--w:1" data-key="KEY_MINUS">-</button><button class="btn key" style="--w:1" data-key="KEY_EQUAL">=</button><button class="btn key" style="--w:2" data-key="KEY_BACKSPACE">Backspace</button></div><div class="key-row"><button class="btn key" style="--w:1.5" data-key="KEY_TAB">Tab</button><button class="btn key" style="--w:1" data-key="KEY_Q">Q</button><button class="btn key" style="--w:1" data-key="KEY_W">W</button><button class="btn key" style="--w:1" data-key="KEY_E">E</button><button class="btn key" style="--w:1" data-key="KEY_R">R</button><button class="btn key" style="--w:1" data-key="KEY_T">T</button><button class="btn key" style="--w:1" data-key="KEY_Y">Y</button><button class="btn key" style="--w:1" data-key="KEY_U">U</button><button class="btn key" style="--w:1" data-key="KEY_I">I</button><button class="btn key" style="--w:1" data-key="KEY_O">O</button><button class="btn key" style="--w:1" data-key="KEY_P">P</button><button class="btn key" style="--w:1" data-key="KEY_LEFTBRACE">[</button><button class="btn key" style="--w:1" data-key="KEY_RIGHTBRACE">]</button><button class="btn key" style="--w:1.5" data-key="KEY_BACKSLASH">\\</button></div><div class="key-row"><button class="btn key" style="--w:1.7" data-key="KEY_CAPSLOCK">Caps</button><button class="btn key" style="--w:1" data-key="KEY_A">A</button><button class="btn key" style="--w:1" data-key="KEY_S">S</button><button class="btn key" style="--w:1" data-key="KEY_D">D</button><button class="btn key" style="--w:1" data-key="KEY_F">F</button><button class="btn key" style="--w:1" data-key="KEY_G">G</button><button class="btn key" style="--w:1" data-key="KEY_H">H</button><button class="btn key" style="--w:1" data-key="KEY_J">J</button><button class="btn key" style="--w:1" data-key="KEY_K">K</button><button class="btn key" style="--w:1" data-key="KEY_L">L</button><button class="btn key" style="--w:1" data-key="KEY_SEMICOLON">;</button><button class="btn key" style="--w:1" data-key="KEY_APOSTROPHE">\'</button><button class="btn key" style="--w:2.3" data-key="KEY_ENTER">Enter</button></div><div class="key-row"><button class="btn key" style="--w:2.2" data-key="KEY_LEFTSHIFT">Shift</button><button class="btn key" style="--w:1" data-key="KEY_Z">Z</button><button class="btn key" style="--w:1" data-key="KEY_X">X</button><button class="btn key" style="--w:1" data-key="KEY_C">C</button><button class="btn key" style="--w:1" data-key="KEY_V">V</button><button class="btn key" style="--w:1" data-key="KEY_B">B</button><button class="btn key" style="--w:1" data-key="KEY_N">N</button><button class="btn key" style="--w:1" data-key="KEY_M">M</button><button class="btn key" style="--w:1" data-key="KEY_COMMA">,</button><button class="btn key" style="--w:1" data-key="KEY_DOT">.</button><button class="btn key" style="--w:1" data-key="KEY_SLASH">/</button><button class="btn key" style="--w:2.6" data-key="KEY_RIGHTSHIFT">Shift</button></div><div class="key-row"><button class="btn key" style="--w:1.5" data-key="KEY_LEFTCTRL">Ctrl</button><button class="btn key" style="--w:1.5" data-key="KEY_LEFTALT">Alt</button><button class="btn key" style="--w:7" data-key="KEY_SPACE">Space</button><button class="btn key" style="--w:1.5" data-key="KEY_RIGHTALT">Alt</button><button class="btn key" style="--w:1.5" data-key="KEY_RIGHTCTRL">Ctrl</button></div><div class="bottom"><div class="nav-cluster"><button class="btn key" data-key="KEY_INSERT">Ins</button><button class="btn key" data-key="KEY_DELETE">Del</button><button class="btn key" data-key="KEY_HOME">Home</button><button class="btn key" data-key="KEY_END">End</button><button class="btn key" data-key="KEY_PAGEUP">PgUp</button><button class="btn key" data-key="KEY_PAGEDOWN">PgDn</button></div><div class="arrows"><button class="btn key au" data-key="KEY_UP">▲</button><button class="btn key al" data-key="KEY_LEFT">◀</button><button class="btn key ad" data-key="KEY_DOWN">▼</button><button class="btn key ar" data-key="KEY_RIGHT">▶</button></div></div></main></div></div><div class="footer">MiSTer Companion Remote by Anime0t4ku</div></div><div class="rotate-tip"><div class="rotate-card"><div class="rotate-icon">↻</div><h2>Rotate your phone</h2><p>The remote is designed to use the available screen best in landscape orientation.</p><button class="btn rotate-dismiss">Continue in portrait</button></div></div><div class="toast"></div><script>\nconst state={ws:null,connected:false,held:new Set(),reconnect:null,heartbeat:null,connecting:false};\nfunction wsURL(){const p=location.protocol===\'https:\'?\'wss\':\'ws\';return `${p}://${location.host}/remote/v1`}\nfunction setStatus(ok){state.connected=ok;document.querySelectorAll(\'.status\').forEach(el=>{el.classList.toggle(\'connected\',ok);el.classList.toggle(\'disconnected\',!ok);el.querySelector(\'span\').textContent=ok?\'Connected\':\'Disconnected\'})}\nfunction connect(){clearTimeout(state.reconnect);if(state.connecting||state.ws?.readyState===WebSocket.OPEN||state.ws?.readyState===WebSocket.CONNECTING)return;state.connecting=true;try{state.ws=new WebSocket(wsURL())}catch(e){state.connecting=false;scheduleReconnect();return}state.ws.onopen=()=>{state.connecting=false;setStatus(true);clearInterval(state.heartbeat);state.heartbeat=setInterval(()=>{if(state.ws?.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:"ping"}))},25000)};state.ws.onclose=()=>{state.connecting=false;clearInterval(state.heartbeat);state.heartbeat=null;setStatus(false);releaseVisuals();scheduleReconnect()};state.ws.onerror=()=>setStatus(false)}\nfunction scheduleReconnect(){clearTimeout(state.reconnect);state.reconnect=setTimeout(connect,1500)}\nfunction send(obj){if(state.ws&&state.ws.readyState===WebSocket.OPEN){state.ws.send(JSON.stringify(obj));return true}showToast(\'Remote is disconnected\');return false}\nfunction ctl(name,action){return send({type:\'controller\',control:[\'up\',\'down\',\'left\',\'right\'].includes(name)?\'dpad\':\'button\',name,action})}\nfunction key(name,action){return send({type:\'keyboard\',key:name,action})}\nfunction systemCommand(command){return send({type:\'system\',command})}\nfunction releaseAll(){if(state.ws&&state.ws.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:\'system\',command:\'release_all\'}));releaseVisuals()}\nfunction releaseVisuals(){state.held.clear();document.querySelectorAll(\'.active\').forEach(el=>el.classList.remove(\'active\'))}\nfunction bindHold(selector,callback){document.querySelectorAll(selector).forEach(el=>{const id=el.dataset.name||el.dataset.key;const down=e=>{e.preventDefault();try{el.setPointerCapture(e.pointerId)}catch(_){}if(state.held.has(el))return;state.held.add(el);el.classList.add(\'active\');callback(id,\'down\')};const up=e=>{e.preventDefault();if(!state.held.has(el))return;state.held.delete(el);el.classList.remove(\'active\');callback(id,\'up\')};el.addEventListener(\'pointerdown\',down);[\'pointerup\',\'pointercancel\',\'lostpointercapture\'].forEach(ev=>el.addEventListener(ev,up));el.addEventListener(\'contextmenu\',e=>e.preventDefault())})}\nfunction showToast(message){const t=document.querySelector(\'.toast\');if(!t)return;t.textContent=message;t.classList.add(\'show\');clearTimeout(t._timer);t._timer=setTimeout(()=>t.classList.remove(\'show\'),2400)}\nfunction setupRotateTip(){const tip=document.querySelector(\'.rotate-tip\');if(!tip)return;const update=()=>{const portrait=matchMedia(\'(orientation: portrait)\').matches&&innerWidth<=700;tip.classList.toggle(\'show\',portrait&&!sessionStorage.getItem(\'remotePortraitDismissed\'))};document.querySelector(\'.rotate-dismiss\')?.addEventListener(\'click\',()=>{sessionStorage.setItem(\'remotePortraitDismissed\',\'1\');tip.classList.remove(\'show\')});addEventListener(\'resize\',update);screen.orientation?.addEventListener?.(\'change\',update);update()}\nwindow.addEventListener(\'blur\',releaseAll);document.addEventListener(\'visibilitychange\',()=>{if(document.hidden)releaseAll()});window.addEventListener(\'beforeunload\',releaseAll);document.addEventListener(\'DOMContentLoaded\',()=>{connect();setupRotateTip()});\n\nconst browserMap={Escape:\'KEY_ESC\',Backspace:\'KEY_BACKSPACE\',Tab:\'KEY_TAB\',Enter:\'KEY_ENTER\',ShiftLeft:\'KEY_LEFTSHIFT\',ShiftRight:\'KEY_RIGHTSHIFT\',ControlLeft:\'KEY_LEFTCTRL\',ControlRight:\'KEY_RIGHTCTRL\',AltLeft:\'KEY_LEFTALT\',AltRight:\'KEY_RIGHTALT\',Space:\'KEY_SPACE\',CapsLock:\'KEY_CAPSLOCK\',ArrowUp:\'KEY_UP\',ArrowDown:\'KEY_DOWN\',ArrowLeft:\'KEY_LEFT\',ArrowRight:\'KEY_RIGHT\',Home:\'KEY_HOME\',End:\'KEY_END\',PageUp:\'KEY_PAGEUP\',PageDown:\'KEY_PAGEDOWN\',Insert:\'KEY_INSERT\',Delete:\'KEY_DELETE\'};for(let i=1;i<=12;i++)browserMap[\'F\'+i]=\'KEY_F\'+i;for(let i=0;i<=9;i++)browserMap[\'Digit\'+i]=\'KEY_\'+i;for(const c of \'ABCDEFGHIJKLMNOPQRSTUVWXYZ\')browserMap[\'Key\'+c]=\'KEY_\'+c;Object.assign(browserMap,{Minus:\'KEY_MINUS\',Equal:\'KEY_EQUAL\',BracketLeft:\'KEY_LEFTBRACE\',BracketRight:\'KEY_RIGHTBRACE\',Backslash:\'KEY_BACKSLASH\',Semicolon:\'KEY_SEMICOLON\',Quote:\'KEY_APOSTROPHE\',Backquote:\'KEY_GRAVE\',Comma:\'KEY_COMMA\',Period:\'KEY_DOT\',Slash:\'KEY_SLASH\'});const physicalHeld=new Set();function fitUI(){const stage=document.querySelector(\'.stage\');if(!stage)return;const vv=window.visualViewport;const vh=vv?vv.height:innerHeight;const top=stage.getBoundingClientRect().top-(vv?vv.offsetTop:0);const aw=Math.max(260,stage.clientWidth);const ah=Math.max(180,vh-top-6);const scale=Math.min(aw/1180,ah/520,1);document.documentElement.style.setProperty(\'--ui-scale\',scale);stage.style.height=(520*scale)+\'px\'}document.addEventListener(\'DOMContentLoaded\',()=>{bindHold(\'.key\',key);fitUI()});addEventListener(\'resize\',fitUI);visualViewport?.addEventListener(\'resize\',fitUI);screen.orientation?.addEventListener?.(\'change\',()=>setTimeout(fitUI,80));window.addEventListener(\'keydown\',e=>{const k=browserMap[e.code];if(!k||physicalHeld.has(k))return;e.preventDefault();physicalHeld.add(k);key(k,\'down\')});window.addEventListener(\'keyup\',e=>{const k=browserMap[e.code];if(!k)return;e.preventDefault();physicalHeld.delete(k);key(k,\'up\')});window.addEventListener(\'blur\',()=>physicalHeld.clear());\n</script></body></html>'.encode("utf-8")



# ---------------------------------------------------------------------------
# v3.0.1 - screenshots, game launching and optional MiSTer Monitor artwork
# ---------------------------------------------------------------------------

MEDIA_ROOTS = [
    "/media/usb0/games", "/media/usb1/games", "/media/usb2/games", "/media/usb3/games",
    "/media/usb4/games", "/media/usb5/games", "/media/usb6/games", "/media/usb7/games",
    "/media/fat/cifs/games", "/media/fat/games",
]
ARTWORK_ROOTS = ["/media/fat"] + ["/media/usb%d" % i for i in range(8)]
SCREENSHOT_ROOT = "/media/fat/screenshots"
TEMP_MGL = "/media/fat/Scripts/.config/companion_remote/companion_launch.mgl"
SCRIPTS_ROOT = "/media/fat/Scripts"
SCRIPT_LAUNCHER = "/tmp/companion_remote_script"

# MGL values are MiSTer core interface parameters, not application-specific
# behaviour. Keep this table small and explicit so unsupported systems fail
# safely instead of guessing a mount slot.
GAME_PROFILES = {
    "Atari2600": {"cores": ["Atari2600"], "media": {".a26": (1, "f", 1), ".bin": (1, "f", 1)}},
    "ATARI5200": {"cores": ["Atari5200"], "media": {".a52": (1, "f", 1), ".bin": (1, "f", 1)}},
    "ATARI7800": {"cores": ["Atari7800"], "media": {".a78": (1, "f", 1), ".bin": (1, "f", 1)}},
    "AtariLynx": {"cores": ["AtariLynx", "Lynx"], "media": {".lnx": (1, "f", 1)}},
    "Coleco": {"cores": ["ColecoVision", "Coleco"], "media": {".col": (1, "f", 1), ".rom": (1, "f", 1), ".bin": (1, "f", 1)}},
    "GAMEBOY": {"cores": ["Gameboy", "GameBoy"], "media": {".gb": (1, "f", 1)}},
    "GBC": {"cores": ["Gameboy", "GameBoy"], "media": {".gbc": (1, "f", 1)}},
    "GBA": {"cores": ["GBA"], "media": {".gba": (1, "f", 0)}},
    "GameGear": {"cores": ["SMS"], "media": {".gg": (1, "f", 2)}},
    "Genesis": {"cores": ["Genesis"], "media": {".bin": (1, "f", 0), ".gen": (1, "f", 0), ".md": (1, "f", 0), ".smd": (1, "f", 0)}},
    "MegaDrive": {"cores": ["MegaDrive"], "media": {".bin": (1, "f", 1), ".gen": (1, "f", 1), ".md": (1, "f", 1), ".smd": (1, "f", 1)}},
    "MegaCD": {"cores": ["MegaCD"], "media": {".cue": (1, "s", 0), ".chd": (1, "s", 0)}},
    "N64": {"cores": ["N64"], "media": {".n64": (1, "f", 1), ".z64": (1, "f", 1), ".v64": (1, "f", 1)}},
    "NEOGEO": {"cores": ["NeoGeo"], "media": {".neo": (1, "f", 1)}},
    "NeoGeo-CD": {"cores": ["NeoGeo"], "media": {".cue": (1, "s", 1), ".chd": (1, "s", 1)}},
    "NES": {"cores": ["NES"], "media": {".nes": (1, "f", 0), ".fds": (1, "f", 0), ".nsf": (1, "f", 0)}},
    "FDS": {"cores": ["NES"], "media": {".fds": (1, "f", 0)}},
    "PSX": {"cores": ["PSX"], "media": {".cue": (1, "s", 1), ".chd": (1, "s", 1)}},
    "S32X": {"cores": ["S32X"], "media": {".32x": (1, "f", 0)}},
    "Saturn": {"cores": ["Saturn"], "media": {".cue": (1, "s", 0), ".chd": (1, "s", 0)}},
    "SG1000": {"cores": ["ColecoVision", "Coleco"], "media": {".sg": (1, "f", 2)}},
    "SGB": {"cores": ["SGB"], "media": {".gb": (1, "f", 1), ".gbc": (1, "f", 1)}},
    "SMS": {"cores": ["SMS"], "media": {".sms": (1, "f", 1), ".sg": (1, "f", 1)}},
    "SNES": {"cores": ["SNES"], "media": {".sfc": (2, "f", 0), ".smc": (2, "f", 0), ".bs": (2, "f", 0)}},
    "TGFX16": {"cores": ["TurboGrafx16"], "media": {".pce": (1, "f", 0), ".bin": (1, "f", 0), ".sgx": (1, "f", 1)}},
    "TGFX16-CD": {"cores": ["TurboGrafx16"], "media": {".cue": (1, "s", 0), ".chd": (1, "s", 0)}},
    "VECTREX": {"cores": ["Vectrex"], "media": {".vec": (1, "f", 1), ".bin": (1, "f", 1), ".rom": (1, "f", 1)}},
    "WonderSwan": {"cores": ["WonderSwan"], "media": {".ws": (1, "f", 1)}},
    "WonderSwanColor": {"cores": ["WonderSwan"], "media": {".wsc": (1, "f", 1)}},
    "3DO": {"cores": ["3DO"], "media": {".cue": (1, "s", 0), ".chd": (1, "s", 0), ".iso": (1, "s", 0)}},
    "CD-i": {"cores": ["CD-i", "CDi"], "media": {".cue": (1, "s", 0), ".chd": (1, "s", 0)}},
}

_artwork_indexes = {}
_game_list_cache = {}
_systems_cache = None
_game_cache_lock = threading.RLock()
_screenshot_lock = threading.RLock()
_script_lock = threading.RLock()
_script_proc = None
_script_path = ""
_script_started = 0.0


def safe_media_path(path):
    try:
        real = os.path.realpath(path)
    except Exception:
        return ""
    allowed = ["/media/fat/", "/media/usb", "/media/fat/cifs/"]
    if not any(real.startswith(prefix) for prefix in allowed):
        return ""
    return real if os.path.isfile(real) else ""


def system_folder(system):
    for root in MEDIA_ROOTS:
        candidate = os.path.join(root, system)
        if os.path.isdir(candidate):
            return candidate
        if os.path.isdir(root):
            try:
                for name in os.listdir(root):
                    if name.lower() == system.lower() and os.path.isdir(os.path.join(root, name)):
                        return os.path.join(root, name)
            except Exception:
                pass
    return ""


def find_core(profile):
    candidates = []
    roots = ["/media/fat/_Console", "/media/fat/_Computer", "/media/fat"]
    aliases = [x.lower() for x in profile.get("cores", [])]
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for name in os.listdir(root):
                if not name.lower().endswith(".rbf"):
                    continue
                stem = name[:-4]
                low = stem.lower()
                score = 0
                for alias in aliases:
                    if low == alias:
                        score = max(score, 100)
                    elif low.startswith(alias + "_") or low.startswith(alias + "-"):
                        score = max(score, 90)
                    elif alias in low:
                        score = max(score, 60)
                if score:
                    candidates.append((score, stem, os.path.join(root, name)))
        except Exception:
            pass
    if not candidates:
        return ""
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    chosen = candidates[0][2]
    rel = os.path.relpath(chosen, "/media/fat")
    return rel[:-4].replace(os.sep, "/")


def list_systems(refresh=False):
    global _systems_cache
    with _game_cache_lock:
        if _systems_cache is not None and not refresh:
            return list(_systems_cache)

    systems = []
    for name, profile in GAME_PROFILES.items():
        folder = system_folder(name)
        if not folder:
            continue
        core = find_core(profile)
        systems.append({"id": name, "name": name, "path": folder, "core": core, "launchable": bool(core)})

    arcade_roots = ["/media/fat/_Arcade"] + ["/media/usb%d/_Arcade" % i for i in range(8)]
    if any(os.path.isdir(p) for p in arcade_roots):
        systems.insert(0, {"id": "Arcade", "name": "Arcade", "path": next((p for p in arcade_roots if os.path.isdir(p)), ""), "core": "MRA", "launchable": True})

    with _game_cache_lock:
        _systems_cache = list(systems)
    return systems


def clean_game_name(path):
    name = os.path.basename(path)
    stem = os.path.splitext(name)[0]
    return stem.replace("_", " ").strip()


def _scan_games(system):
    if system == "Arcade":
        roots = [p for p in (["/media/fat/_Arcade"] + ["/media/usb%d/_Arcade" % i for i in range(8)]) if os.path.isdir(p)]
        exts = {".mra"}
    else:
        profile = GAME_PROFILES.get(system)
        if not profile:
            return []
        folder = system_folder(system)
        roots = [folder] if folder else []
        exts = set(profile.get("media", {}).keys()) | {".mgl"}

    results = []
    for root in roots:
        for current, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for filename in files:
                if os.path.splitext(filename)[1].lower() not in exts:
                    continue
                path = os.path.join(current, filename)
                results.append({
                    "system": system,
                    "name": clean_game_name(path),
                    "path": path,
                    "artwork": "/api/artwork?system=%s&path=%s" % (
                        urllib.parse.quote(system, safe=""), urllib.parse.quote(path, safe="")
                    ),
                })
    results.sort(key=lambda x: x["name"].lower())
    return results


def list_games(system, search="", limit=4000, refresh=False):
    query = (search or "").lower().strip()

    if system == "All":
        combined = []
        for item in list_systems():
            if not item.get("launchable"):
                continue
            remaining = max(0, limit - len(combined))
            if remaining <= 0:
                break
            combined.extend(list_games(item["id"], search, limit=remaining, refresh=refresh))
        combined.sort(key=lambda x: (x["system"].lower(), x["name"].lower()))
        return combined[:limit]

    with _game_cache_lock:
        cached = _game_list_cache.get(system)
    if cached is None or refresh:
        cached = _scan_games(system)
        with _game_cache_lock:
            _game_list_cache[system] = cached

    if not query:
        return list(cached[:limit])

    results = []
    for game in cached:
        if query in game["name"].lower() or query in game["path"].lower():
            results.append(game)
            if len(results) >= limit:
                break
    return results


def list_games_page(system, search="", offset=0, limit=200, refresh=False):
    try:
        offset = max(0, int(offset))
    except Exception:
        offset = 0
    try:
        limit = int(limit)
    except Exception:
        limit = 200
    limit = max(1, min(limit, 500))

    # Keep the cached per-system scan as the source of truth, but only send a
    # small page to the browser. This avoids giant JSON responses for large
    # libraries and makes the explicit All view practical.
    all_games = list_games(system, search, limit=100000, refresh=refresh)
    total = len(all_games)
    page = all_games[offset:offset + limit]
    return page, total, (offset + len(page) < total)


def artwork_dir(system):
    aliases = [system]
    if system == "Arcade":
        aliases = ["Arcade"]
    for root in ARTWORK_ROOTS:
        for alias in aliases:
            path = os.path.join(root, "docs", alias, "Artwork")
            if os.path.isdir(path):
                return path
    return ""


def artwork_index(directory):
    path = os.path.join(directory, "index.tsv")
    try:
        stamp = os.path.getmtime(path)
    except Exception:
        return {}
    cached = _artwork_indexes.get(path)
    if cached and cached[0] == stamp:
        return cached[1]
    data = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line or line.startswith("#"):
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 4:
                    data[parts[0].lower()] = parts[3]
    except Exception:
        return {}
    _artwork_indexes[path] = (stamp, data)
    return data


def artwork_for_game(system, game_path):
    directory = artwork_dir(system)
    if not directory:
        return ""
    key = os.path.splitext(os.path.basename(game_path))[0]
    direct = os.path.join(directory, key + ".jpg")
    if os.path.isfile(direct):
        return direct
    index = artwork_index(directory)
    mapped = index.get(key.lower(), "")
    if mapped:
        candidate = os.path.join(directory, mapped + ".jpg")
        if os.path.isfile(candidate):
            return candidate
    tail = re.search(r"\(([^()]*)\)\s*$", key)
    if tail:
        candidate = os.path.join(directory, tail.group(1) + ".jpg")
        if os.path.isfile(candidate):
            return candidate
    return ""


def make_mgl(system, game_path):
    profile = GAME_PROFILES.get(system)
    if not profile:
        raise ValueError("Unsupported system: %s" % system)
    ext = os.path.splitext(game_path)[1].lower()
    media = profile.get("media", {}).get(ext)
    if not media:
        raise ValueError("Unsupported %s file for %s" % (ext or "media", system))
    rbf = find_core(profile)
    if not rbf:
        raise ValueError("No compatible installed core found for %s" % system)
    base = system_folder(system)
    if not base:
        raise ValueError("Game folder not found for %s" % system)
    try:
        rel = os.path.relpath(game_path, base).replace(os.sep, "/")
    except Exception:
        rel = os.path.basename(game_path)
    if rel.startswith("../"):
        raise ValueError("Game is outside the configured %s games folder" % system)
    delay, kind, index = media
    xml = (
        "<mistergamedescription>\n"
        "  <rbf>%s</rbf>\n"
        "  <file delay=\"%d\" type=\"%s\" index=\"%d\" path=\"%s\"/>\n"
        "</mistergamedescription>\n"
    ) % (xml_escape(rbf), delay, kind, index, xml_escape(rel, quote=True))
    with open(TEMP_MGL, "w", encoding="utf-8") as f:
        f.write(xml)
    return TEMP_MGL


def launch_game(system, path):
    path = safe_media_path(path)
    if not path:
        raise ValueError("Game path does not exist or is outside MiSTer storage")
    ext = os.path.splitext(path)[1].lower()
    if ext in (".mra", ".mgl", ".rbf"):
        target = path
    else:
        target = make_mgl(system, path)
    state.release_all()
    command = "load_core %s" % target
    try:
        with open("/dev/MiSTer_cmd", "w") as f:
            f.write(command + "\n")
    except Exception as e:
        raise RuntimeError("Unable to send launch command: %s" % e)
    return target


def _screenshot_snapshot():
    files = {}
    if not os.path.isdir(SCREENSHOT_ROOT):
        return files
    try:
        for current, dirs, names in os.walk(SCREENSHOT_ROOT):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in names:
                if not name.lower().endswith(".png"):
                    continue
                path = os.path.join(current, name)
                try:
                    st = os.stat(path)
                    files[path] = (getattr(st, "st_mtime_ns", int(st.st_mtime * 1000000000)), st.st_size)
                except OSError:
                    pass
    except OSError:
        pass
    return files


def latest_screenshot_path():
    files = _screenshot_snapshot()
    if not files:
        return ""
    return max(files, key=lambda p: (files[p][0], files[p][1], p))


def _png_is_complete(data):
    # A PNG can already have a valid signature while MiSTer is still writing
    # the image. Only serve it after the final IEND chunk is present.
    return (
        data.startswith(b"\x89PNG\r\n\x1a\n")
        and data.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82")
    )


def _read_png(path, require_complete=True):
    if not path or not os.path.isfile(path):
        raise RuntimeError("No MiSTer screenshot is available")
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("MiSTer screenshot is not a valid PNG")
    if require_complete and not _png_is_complete(data):
        raise RuntimeError("MiSTer screenshot is still being written")
    return data


def _trigger_mister_screenshot():
    # MiSTer accepts Alt+ScrollLock as an alternate screenshot shortcut.
    # Drive it through the daemon's own uinput keyboard so MiSTer performs
    # the capture and writes the PNG itself.
    state.release_all()
    alt = KEY_CODES["KEY_LEFTALT"]
    scroll = KEY_CODES["KEY_SCROLLLOCK"]
    state.keyboard_key(alt, True)
    try:
        state.keyboard_key(scroll, True)
        time.sleep(0.060)
        state.keyboard_key(scroll, False)
    finally:
        state.keyboard_key(alt, False)


def capture_screenshot(timeout=6.0):
    with _screenshot_lock:
        before = _screenshot_snapshot()
        _trigger_mister_screenshot()
        deadline = time.time() + timeout
        last_sizes = {}
        stable_counts = {}
        while time.time() < deadline:
            time.sleep(0.10)
            after = _screenshot_snapshot()
            changed = []
            for path, meta in after.items():
                if before.get(path) != meta and meta[1] > 8:
                    changed.append(path)
            if not changed:
                continue

            newest = max(changed, key=lambda p: (after[p][0], after[p][1], p))
            size = after[newest][1]
            if last_sizes.get(newest) == size:
                stable_counts[newest] = stable_counts.get(newest, 0) + 1
            else:
                last_sizes[newest] = size
                stable_counts[newest] = 0

            # Require both a complete PNG IEND marker and at least one stable
            # size observation. This prevents serving a file while MiSTer is
            # still appending scanlines/chunks to it.
            if stable_counts.get(newest, 0) >= 1:
                try:
                    return _read_png(newest, require_complete=True)
                except RuntimeError:
                    pass

        raise RuntimeError("MiSTer did not finish creating the screenshot in time")


def safe_script_path(path):
    value = str(path or "").strip()
    if not value:
        raise ValueError("Script path is required")
    if "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError("Invalid script path")
    if not os.path.isabs(value):
        value = os.path.join(SCRIPTS_ROOT, value)
    real = os.path.realpath(value)
    root = os.path.realpath(SCRIPTS_ROOT)
    if real == root or not real.startswith(root + os.sep):
        raise ValueError("Script must be inside /media/fat/Scripts")
    if not real.lower().endswith(".sh"):
        raise ValueError("Only .sh scripts can be launched")
    if not os.path.isfile(real):
        raise ValueError("Script not found")
    return real


def list_scripts():
    results = []
    root_real = os.path.realpath(SCRIPTS_ROOT)
    if not os.path.isdir(root_real):
        return results
    for base, dirs, files in os.walk(root_real):
        dirs[:] = sorted([d for d in dirs if not d.startswith(".") and d != ".config"], key=str.lower)
        for filename in sorted(files, key=str.lower):
            if filename.startswith(".") or not filename.lower().endswith(".sh"):
                continue
            path = os.path.join(base, filename)
            try:
                real = os.path.realpath(path)
                if not real.startswith(root_real + os.sep) or not os.path.isfile(real):
                    continue
                rel = os.path.relpath(real, root_real).replace(os.sep, "/")
                name = os.path.splitext(os.path.basename(real))[0].replace("_", " ")
                results.append({"name": name, "path": real, "relative": rel})
            except Exception:
                continue
    results.sort(key=lambda item: (item["relative"].count("/"), item["relative"].lower()))
    return results


def _switch_tty(number):
    command = shutil_which("chvt") or "/bin/chvt"
    try:
        return subprocess.call([command, str(int(number))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except Exception:
        return False


def script_status():
    global _script_proc, _script_path, _script_started
    with _script_lock:
        running_now = bool(_script_proc is not None and _script_proc.poll() is None)
        if not running_now and _script_proc is not None:
            _script_proc = None
            _script_path = ""
            _script_started = 0.0
        return {
            "running": running_now,
            "path": _script_path if running_now else "",
            "name": os.path.basename(_script_path) if running_now else "",
            "started": _script_started if running_now else 0,
        }


def _watch_script(proc):
    global _script_proc, _script_path, _script_started
    try:
        proc.wait()
    except Exception:
        pass
    with _script_lock:
        if _script_proc is proc:
            _script_proc = None
            _script_path = ""
            _script_started = 0.0
    time.sleep(0.15)
    _switch_tty(1)


def launch_script(path):
    global _script_proc, _script_path, _script_started
    script = safe_script_path(path)
    with _script_lock:
        if _script_proc is not None and _script_proc.poll() is None:
            raise RuntimeError("Another script is already running")

        script_dir = os.path.dirname(script)
        quoted_script = shlex.quote(script)
        quoted_dir = shlex.quote(script_dir)
        launcher = "\n".join([
            "#!/bin/bash",
            "export LC_ALL=en_US.UTF-8",
            "export HOME=/root",
            "export LESSKEY=/media/fat/linux/lesskey",
            "cd -- %s" % quoted_dir,
            "if [ -x %s ]; then exec %s; else exec /bin/bash %s; fi" % (quoted_script, quoted_script, quoted_script),
            "",
        ])
        with open(SCRIPT_LAUNCHER, "w") as handle:
            handle.write(launcher)
        os.chmod(SCRIPT_LAUNCHER, 0o700)

        agetty = shutil_which("agetty") or "/sbin/agetty"
        if not os.path.exists(agetty):
            raise RuntimeError("agetty is not available")

        _switch_tty(2)
        proc = subprocess.Popen(
            [agetty, "-a", "root", "-l", SCRIPT_LAUNCHER, "--nohostname", "-L", "tty2", "linux"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
            close_fds=True,
        )
        _script_proc = proc
        _script_path = script
        _script_started = time.time()
        threading.Thread(target=_watch_script, args=(proc,), daemon=True).start()
        return script_status()


def stop_script():
    global _script_proc, _script_path, _script_started
    with _script_lock:
        proc = _script_proc
        if proc is None or proc.poll() is not None:
            _script_proc = None
            _script_path = ""
            _script_started = 0.0
            _switch_tty(1)
            return False
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
    try:
        proc.wait(timeout=2.0)
    except Exception:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    with _script_lock:
        if _script_proc is proc:
            _script_proc = None
            _script_path = ""
            _script_started = 0.0
    _switch_tty(1)
    return True


def open_script_console():
    status = script_status()
    if not status["running"]:
        raise RuntimeError("No script is currently running")
    if not _switch_tty(2):
        raise RuntimeError("Unable to switch to the script console")
    return status


def close_script_console():
    if not _switch_tty(1):
        raise RuntimeError("Unable to return to the MiSTer console")
    return script_status()


def shutil_which(command):
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        path = os.path.join(directory, command)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return ""


GAMES_HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover"><meta name="theme-color" content="#120f1c"><title>Games · MiSTer Companion Remote</title><style>
:root{--bg:#120f1c;--panel:#1b1628;--panel2:#2b2340;--text:#f2ecff;--muted:#b5a9c9;--accent:#8b5cf6;--accent2:#a78bfa;--ok:#39d98a;--danger:#d95768;--border:#3a2f55;--shadow:0 18px 55px rgba(0,0,0,.42)}*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:radial-gradient(circle at top,#261c3d 0,#120f1c 48%,#0b0911 100%);color:var(--text);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.shell{width:min(1220px,100%);margin:auto;padding:16px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 16px;background:rgba(27,22,40,.94);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow)}.brand{display:flex;align-items:center;gap:12px}.brand img{width:74px}.brand h1{font-size:1rem;margin:0}.brand p{margin:3px 0 0;color:var(--muted);font-size:.78rem}.nav{display:flex;gap:8px;margin:12px 0}.nav a{flex:1;text-align:center;text-decoration:none;color:var(--text);background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:10px;font-weight:800}.nav a.active,.nav a:hover{background:var(--accent);border-color:var(--accent2)}.card{background:rgba(27,22,40,.96);border:1px solid var(--border);border-radius:22px;box-shadow:var(--shadow)}.tools{display:grid;grid-template-columns:minmax(180px,280px) minmax(150px,190px) 1fr;gap:10px;padding:14px;border-bottom:1px solid var(--border)}.tools select,.tools input{width:100%;min-height:46px;border-radius:12px;border:1px solid var(--border);background:var(--panel2);color:var(--text);padding:0 12px;font:inherit}.summary{color:var(--muted);font-size:.76rem;padding:10px 14px 0}.games{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px;padding:14px}.game{overflow:hidden;background:var(--panel2);border:1px solid var(--border);border-radius:16px;cursor:pointer;transition:.12s}.game:hover{transform:translateY(-2px);border-color:var(--accent2)}.art{height:180px;background:#100c18;display:flex;align-items:center;justify-content:center;color:var(--muted);overflow:hidden}.art img{width:100%;height:100%;object-fit:contain}.game h3{font-size:.9rem;margin:10px 11px 4px;line-height:1.25}.game p{color:var(--muted);font-size:.72rem;margin:0 11px 12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.system-tag{display:inline-block;color:var(--accent2);font-size:.68rem;font-weight:800;margin:8px 11px 0}.games.list-view{display:block}.games.list-view .game{display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-areas:'title system' 'path system';align-items:center;gap:2px 12px;padding:10px 12px;margin-bottom:7px;border-radius:12px}.games.list-view .game h3{grid-area:title;margin:0;font-size:.9rem}.games.list-view .game p{grid-area:path;margin:2px 0 0;font-size:.72rem}.games.list-view .system-tag{grid-area:system;margin:0;white-space:nowrap}.empty{padding:40px;text-align:center;color:var(--muted)}.load-more-wrap{text-align:center;padding:0 14px 18px}.load-more{border:1px solid #5b4a7a;background:linear-gradient(180deg,#352a4f,#241d35);color:var(--text);border-radius:12px;min-height:44px;padding:0 24px;font-weight:800;cursor:pointer}.load-more[hidden]{display:none}.toast{position:fixed;left:50%;bottom:20px;transform:translate(-50%,20px);opacity:0;background:#2b2340;border:1px solid #5b4a7a;border-radius:12px;padding:11px 16px;z-index:120;transition:.2s}.toast.show{opacity:1;transform:translate(-50%,0)}@media(max-width:700px){.map-item{grid-template-columns:minmax(80px,.8fr) minmax(0,1.2fr)}.map-listen{grid-column:2;width:100%}.shell{padding:7px}.brand img{width:46px}.brand p{display:none}.nav{gap:5px}.nav a{padding:7px 3px;font-size:.72rem}.tools{grid-template-columns:1fr;padding:8px}.games{grid-template-columns:repeat(2,minmax(0,1fr));padding:8px;gap:8px}.art{height:145px}}
</style></head><body><div class="shell"><header class="topbar"><div class="brand"><img src="/assets/logo.png" alt="MiSTer Companion"><div><h1>MiSTer Companion Remote</h1><p>Browser remote v4.0.3</p></div></div></header><nav class="nav"><a href="/">Home</a><a href="/controller">Controller</a><a href="/keyboard">Keyboard</a><a href="/games" class="active">Games</a><a href="/scripts">Scripts</a><a href="/bluebridge">BlueBridge</a></nav><main class="card"><div class="tools"><select id="system"><option>Loading systems…</option></select><select id="view" aria-label="Game view"><option value="artwork">Artwork view</option><option value="list">List view</option></select><input id="search" type="search" placeholder="Search games"></div><div class="summary" id="summary"></div><div class="games" id="games"><div class="empty">Loading systems…</div></div><div class="load-more-wrap"><button class="load-more" id="more" hidden>Load more</button></div></main></div><div class="toast"></div><script>
const systemSelect=document.querySelector('#system'),viewSelect=document.querySelector('#view'),search=document.querySelector('#search'),games=document.querySelector('#games'),summary=document.querySelector('#summary'),more=document.querySelector('#more'),toast=document.querySelector('.toast');
let systems=[],offset=0,activeController=null,requestSerial=0,loadingMore=false,loadedGames=[];const PAGE=200;
let viewMode=localStorage.getItem('companionGamesView')||'artwork';if(!['artwork','list'].includes(viewMode))viewMode='artwork';viewSelect.value=viewMode;
function note(s){toast.textContent=s;toast.classList.add('show');clearTimeout(toast._t);toast._t=setTimeout(()=>toast.classList.remove('show'),2400)}
async function json(url,options={}){const r=await fetch(url,options);let j;try{j=await r.json()}catch(_){throw new Error('Invalid response from Companion Remote')};if(!r.ok||j.ok===false)throw new Error(j.message||('Request failed ('+r.status+')'));return j}
function current(){return systemSelect.value||'All'}
function updatePlaceholder(){const id=current(),s=systems.find(x=>x.id===id);search.placeholder=id==='All'?'Search all games':'Search '+(s?s.name:id)}
async function loadSystems(){try{const j=await json('/api/games/systems');systems=(j.systems||[]).filter(s=>s.launchable);systemSelect.innerHTML='';const all=document.createElement('option');all.value='All';all.textContent='All systems';systemSelect.appendChild(all);for(const s of systems){const o=document.createElement('option');o.value=s.id;o.textContent=s.name;systemSelect.appendChild(o)}if(systems.length)systemSelect.value=systems[0].id;else systemSelect.value='All';updatePlaceholder();await loadGames(true)}catch(e){games.innerHTML='<div class="empty">'+e.message+'</div>';summary.textContent='';more.hidden=true}}
function attachLaunch(el,g){el.addEventListener('click',async()=>{if(!confirm('Launch '+g.name+'?'))return;try{await json('/api/games/launch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({system:g.system,path:g.path})});note('Launching '+g.name+'…')}catch(e){note(e.message)}})}
function renderGame(g,viewSystem){const el=document.createElement('article');el.className='game';if(viewMode==='list'){el.innerHTML='<h3></h3><p></p>'+(viewSystem==='All'?'<span class="system-tag"></span>':'');if(viewSystem==='All')el.querySelector('.system-tag').textContent=g.system}else{el.innerHTML='<div class="art"><img loading="lazy" alt=""></div>'+(viewSystem==='All'?'<span class="system-tag"></span>':'')+'<h3></h3><p></p>';const img=el.querySelector('img');img.src=g.artwork;img.onerror=()=>{const box=img.parentElement;box.textContent='No artwork'};if(viewSystem==='All')el.querySelector('.system-tag').textContent=g.system}el.querySelector('h3').textContent=g.name;el.querySelector('p').textContent=g.path;attachLaunch(el,g);games.appendChild(el)}
function renderLoaded(viewSystem){games.classList.toggle('list-view',viewMode==='list');games.innerHTML='';for(const g of loadedGames)renderGame(g,viewSystem);if(!loadedGames.length)games.innerHTML='<div class="empty">No matching games found.</div>'}
async function loadGames(reset){
  if(!reset&&loadingMore)return;
  const viewSystem=current(),query=search.value;
  if(reset){
    if(activeController)activeController.abort();
    activeController=new AbortController();
    requestSerial++;
    offset=0;loadingMore=false;loadedGames=[];
    games.classList.toggle('list-view',viewMode==='list');
    games.innerHTML='<div class="empty">Loading '+(viewSystem==='All'?'all systems':viewSystem)+'…</div>';
    summary.textContent='';more.hidden=true;
  }else{
    if(!activeController)activeController=new AbortController();
    loadingMore=true;
  }
  const serial=requestSerial,controller=activeController,startOffset=offset;
  try{
    const url='/api/games/list?system='+encodeURIComponent(viewSystem)+'&q='+encodeURIComponent(query)+'&offset='+startOffset+'&limit='+PAGE;
    const j=await json(url,{signal:controller.signal});
    if(serial!==requestSerial||controller.signal.aborted||viewSystem!==current()||query!==search.value)return;
    loadedGames.push(...(j.games||[]));
    renderLoaded(viewSystem);
    offset=startOffset+(j.games||[]).length;
    const total=Number(j.total||0);
    summary.textContent=total+' game'+(total===1?'':'s')+(viewSystem==='All'?' across all systems':' in '+viewSystem);
    more.hidden=!j.has_more;
  }catch(e){
    if(e.name==='AbortError')return;
    if(serial!==requestSerial)return;
    if(reset)games.innerHTML='<div class="empty">'+e.message+'</div>';else note(e.message);
    more.hidden=true;
  }finally{
    if(serial===requestSerial)loadingMore=false;
  }
}
systemSelect.addEventListener('change',()=>{updatePlaceholder();loadGames(true)});
viewSelect.addEventListener('change',()=>{viewMode=viewSelect.value;localStorage.setItem('companionGamesView',viewMode);renderLoaded(current())});
let timer;search.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>loadGames(true),250)});
more.addEventListener('click',()=>loadGames(false));
loadSystems();
</script></body></html>'''.encode("utf-8")


SCRIPTS_HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover"><meta name="theme-color" content="#120f1c"><title>Scripts - MiSTer Companion Remote</title><style>
:root{--bg:#120f1c;--panel:#1b1628;--panel2:#2b2340;--text:#f2ecff;--muted:#b5a9c9;--accent:#8b5cf6;--accent2:#a78bfa;--danger:#d95768;--border:#3a2f55;--shadow:0 18px 55px rgba(0,0,0,.42)}*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:radial-gradient(circle at top,#261c3d 0,#120f1c 48%,#0b0911 100%);color:var(--text);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.shell{width:min(1220px,100%);margin:auto;padding:16px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 16px;background:rgba(27,22,40,.94);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow)}.brand{display:flex;align-items:center;gap:12px}.brand img{width:74px}.brand h1{font-size:1rem;margin:0}.brand p{margin:3px 0 0;color:var(--muted);font-size:.78rem}.nav{display:flex;gap:8px;margin:12px 0}.nav a{flex:1;text-align:center;text-decoration:none;color:var(--text);background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:10px;font-weight:800}.nav a.active,.nav a:hover{background:var(--accent);border-color:var(--accent2)}.card{background:rgba(27,22,40,.96);border:1px solid var(--border);border-radius:22px;box-shadow:var(--shadow)}.tools{display:grid;grid-template-columns:1fr auto auto;gap:10px;padding:14px;border-bottom:1px solid var(--border)}input{min-height:46px;border-radius:12px;border:1px solid var(--border);background:var(--panel2);color:var(--text);padding:0 12px;font:inherit}.btn{border:1px solid #5b4a7a;background:linear-gradient(180deg,#352a4f,#241d35);color:var(--text);border-radius:12px;min-height:46px;padding:0 16px;font-weight:800;cursor:pointer}.btn.danger{background:#48232d;border-color:#7a3848}.btn:disabled{opacity:.45;cursor:not-allowed}.statusline{padding:12px 14px;color:var(--muted);border-bottom:1px solid var(--border)}.statusline strong{color:var(--text)}.scripts{padding:12px}.script{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;padding:12px 14px;margin-bottom:8px;background:var(--panel2);border:1px solid var(--border);border-radius:14px}.script h3{margin:0 0 4px;font-size:.92rem}.script p{margin:0;color:var(--muted);font-size:.72rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.empty{padding:40px;text-align:center;color:var(--muted)}.toast{position:fixed;left:50%;bottom:20px;transform:translate(-50%,20px);opacity:0;background:#2b2340;border:1px solid #5b4a7a;border-radius:12px;padding:11px 16px;z-index:120;transition:.2s}.toast.show{opacity:1;transform:translate(-50%,0)}@media(max-width:700px){.map-item{grid-template-columns:minmax(80px,.8fr) minmax(0,1.2fr)}.map-listen{grid-column:2;width:100%}.shell{padding:7px}.brand img{width:46px}.brand p{display:none}.nav{gap:5px}.nav a{padding:7px 3px;font-size:.68rem}.tools{grid-template-columns:1fr 1fr}.tools input{grid-column:1/-1}.script{grid-template-columns:1fr}.script .btn{width:100%}}
</style></head><body><div class="shell"><header class="topbar"><div class="brand"><img src="/assets/logo.png" alt="MiSTer Companion"><div><h1>MiSTer Companion Remote</h1><p>Browser remote v4.0.3</p></div></div></header><nav class="nav"><a href="/">Home</a><a href="/controller">Controller</a><a href="/keyboard">Keyboard</a><a href="/games">Games</a><a href="/scripts" class="active">Scripts</a><a href="/bluebridge">BlueBridge</a></nav><main class="card"><div class="tools"><input id="search" type="search" placeholder="Search scripts"><button class="btn" id="console">Open console</button><button class="btn danger" id="stop">Stop script</button></div><div class="statusline" id="status">Checking script status...</div><div class="scripts" id="scripts"><div class="empty">Loading scripts...</div></div></main></div><div class="toast"></div><script>
const scriptsEl=document.querySelector('#scripts'),search=document.querySelector('#search'),statusEl=document.querySelector('#status'),consoleBtn=document.querySelector('#console'),stopBtn=document.querySelector('#stop'),toast=document.querySelector('.toast');let scripts=[];
function note(s){toast.textContent=s;toast.classList.add('show');clearTimeout(toast._t);toast._t=setTimeout(()=>toast.classList.remove('show'),2400)}
async function json(url,options={}){const r=await fetch(url,options);let j;try{j=await r.json()}catch(_){throw new Error('Invalid response from Companion Remote')};if(!r.ok||j.ok===false)throw new Error(j.message||('Request failed ('+r.status+')'));return j}
function render(){const q=search.value.trim().toLowerCase(),items=scripts.filter(s=>!q||s.name.toLowerCase().includes(q)||s.relative.toLowerCase().includes(q));scriptsEl.innerHTML='';if(!items.length){scriptsEl.innerHTML='<div class="empty">No matching scripts found.</div>';return}for(const s of items){const row=document.createElement('article');row.className='script';const info=document.createElement('div');const h=document.createElement('h3');h.textContent=s.name;const p=document.createElement('p');p.textContent=s.relative;info.append(h,p);const b=document.createElement('button');b.className='btn';b.textContent='Launch';b.onclick=()=>launch(s);row.append(info,b);scriptsEl.appendChild(row)}}
function showStatus(st){if(st&&st.running){statusEl.innerHTML='<strong>Running:</strong> '+(st.name||st.path);consoleBtn.disabled=false;stopBtn.disabled=false}else{statusEl.textContent='No script is currently running.';consoleBtn.disabled=true;stopBtn.disabled=true}}
async function load(){try{const j=await json('/api/scripts/list');scripts=j.scripts||[];render();showStatus(j.status)}catch(e){scriptsEl.innerHTML='<div class="empty">'+e.message+'</div>'}}
async function refreshStatus(){try{const j=await json('/api/scripts/status');showStatus(j.status)}catch(_){}}
async function launch(s){if(!confirm('Launch '+s.name+'?'))return;try{const j=await json('/api/scripts/launch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:s.path})});showStatus(j.status);note('Launching '+s.name+'...')}catch(e){note(e.message)}}
consoleBtn.onclick=async()=>{try{const j=await json('/api/scripts/console',{method:'POST'});showStatus(j.status);note('Script console opened on MiSTer')}catch(e){note(e.message)}};
stopBtn.onclick=async()=>{if(!confirm('Stop the active script?'))return;try{const j=await json('/api/scripts/stop',{method:'POST'});showStatus(j.status);note(j.message)}catch(e){note(e.message)}};
search.addEventListener('input',render);load();setInterval(refreshStatus,2000);
</script></body></html>'''.encode("utf-8")



BLUEBRIDGE_HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#120f1c"><title>MC BlueBridge</title><style>
:root{--panel:#1b1628;--panel2:#241d35;--panel3:#2d2442;--text:#f4efff;--muted:#b7acca;--accent:#8b5cf6;--accent2:#a78bfa;--ok:#39d98a;--danger:#e16978;--border:#3b3055;--shadow:0 18px 50px rgba(0,0,0,.35)}*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:radial-gradient(circle at top,#281d40,#120f1c 50%,#0b0911);color:var(--text);font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif}button,input,select{font:inherit}.shell{width:min(1180px,100%);margin:auto;padding:14px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;background:rgba(27,22,40,.96);border:1px solid var(--border);border-radius:18px;padding:11px 15px;box-shadow:var(--shadow)}.brand{display:flex;align-items:center;gap:11px}.brand img{width:58px}.brand h1{margin:0;font-size:1rem}.brand p{margin:3px 0 0;color:var(--muted);font-size:.76rem}.pill{display:inline-flex;align-items:center;gap:7px;padding:7px 10px;border:1px solid var(--border);border-radius:999px;background:var(--panel2);font-size:.78rem;font-weight:800}.dot{width:9px;height:9px;border-radius:50%;background:var(--danger)}.pill.ok .dot{background:var(--ok)}.nav{display:flex;gap:7px;margin:10px 0}.nav a{flex:1;text-align:center;text-decoration:none;color:var(--text);background:var(--panel);border:1px solid var(--border);border-radius:11px;padding:9px 5px;font-size:.8rem;font-weight:800}.nav a.active{background:var(--accent);border-color:var(--accent2)}.panel{background:rgba(27,22,40,.96);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow);padding:15px;margin-bottom:12px}.btn{border:1px solid #5b4a7a;background:linear-gradient(180deg,#382c52,#251d37);color:var(--text);border-radius:10px;padding:9px 12px;font-weight:800;cursor:pointer;min-height:38px}.btn.primary{background:var(--accent);border-color:var(--accent2)}.btn.danger{background:#4a242e;border-color:#7c3b49}.btn.small{min-height:32px;padding:6px 9px;font-size:.74rem}.btn:disabled{opacity:.4;cursor:default}.subtle{color:var(--muted);font-size:.76rem;line-height:1.45}.controller-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.controller-head h2{margin:3px 0 4px;font-size:1.3rem}.status-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:7px;margin-top:13px}.stat{background:#171222;border:1px solid var(--border);border-radius:10px;padding:9px}.stat span{display:block;color:var(--muted);font-size:.68rem}.stat strong{display:block;font-size:.8rem;margin-top:3px;word-break:break-word}.stat.action{cursor:pointer;transition:border-color .15s,background .15s}.stat.action:hover{border-color:var(--accent2);background:var(--panel2)}.under-card{display:flex;gap:8px;margin:-2px 0 12px}.under-card .btn{flex:1}.toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}.toolbar h2,.toolbar h3{margin:0}.profile-pills{display:flex;gap:7px;overflow:auto;padding:4px 0 9px}.profile-pill{border:1px solid var(--border);background:var(--panel2);color:var(--text);border-radius:999px;padding:8px 12px;white-space:nowrap;cursor:pointer}.profile-pill.active{background:var(--accent);border-color:var(--accent2)}.editor-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin:10px 0}.editor-head h2{margin:0}.actions{display:flex;gap:7px;flex-wrap:wrap}.tabs{display:flex;gap:6px;border-bottom:1px solid var(--border);padding-bottom:9px;margin-bottom:13px;overflow:auto}.tab{border:0;background:transparent;color:var(--muted);padding:8px 11px;border-radius:9px;font-weight:800;cursor:pointer;white-space:nowrap}.tab.active{background:var(--panel3);color:var(--text)}.tabpage{display:none}.tabpage.active{display:block}.surface{background:var(--panel2);border:1px solid var(--border);border-radius:14px;padding:14px;margin-bottom:10px}.surface h3{margin:0 0 5px}.notice{padding:11px 12px;background:#171222;border:1px solid var(--border);border-radius:11px;color:var(--muted);font-size:.76rem;line-height:1.45;margin-bottom:10px}.map-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.map-item{display:grid;grid-template-columns:minmax(95px,.8fr) minmax(130px,1.2fr) auto;align-items:center;gap:8px;padding:9px;background:#171222;border-radius:10px;border:1px solid transparent}.map-item.hit{border-color:var(--accent2)}select,input[type=text],input[type=number]{width:100%;background:#100d18;color:var(--text);border:1px solid var(--border);border-radius:10px;padding:9px}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.form-group label{display:block;font-size:.76rem;font-weight:800;margin-bottom:5px}.switch-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 12px;background:#171222;border-radius:10px;margin-bottom:10px}.switch{position:relative;width:46px;height:26px;flex:none}.switch input{opacity:0;width:0;height:0}.slider{position:absolute;inset:0;background:#4b405c;border-radius:999px}.slider:before{content:"";position:absolute;width:20px;height:20px;left:3px;top:3px;border-radius:50%;background:#fff;transition:.15s}.switch input:checked+.slider{background:var(--accent)}.switch input:checked+.slider:before{transform:translateX(20px)}.button-checks{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.check{display:flex;gap:6px;align-items:center;background:#171222;border-radius:9px;padding:8px;font-size:.75rem}.macro-card{background:#171222;border:1px solid var(--border);border-radius:12px;padding:12px;margin-bottom:9px}.macro-head{display:flex;justify-content:space-between;gap:10px;align-items:center}.macro-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}.macro-output{margin-top:10px}.capture-select{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:7px}.paired-list{display:grid;gap:8px;margin-top:12px}.paired-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;background:var(--panel2);border:1px solid var(--border);border-radius:13px;padding:12px}.paired-row.connected{border-color:var(--accent2)}.paired-row h3{margin:0 0 4px;font-size:.92rem}.firmware-update{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(220px,1fr) auto;gap:9px;align-items:end;margin-top:12px}.firmware-update input[type=file]{width:100%;background:#100d18;color:var(--text);border:1px solid var(--border);border-radius:10px;padding:8px}.firmware-status{margin-top:9px}.firmware-status.busy{color:var(--accent2)}.firmware-status.error{color:var(--danger)}.firmware-status.warning{color:#e7bd63}.maintenance-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.maintenance-actions .btn{flex:1;min-width:180px}.search{margin-top:10px}.tester-buttons{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.test-key{padding:10px;background:#171222;border:1px solid var(--border);border-radius:10px;text-align:center;font-size:.75rem}.test-key.on{background:var(--accent);border-color:var(--accent2)}.analog-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:10px}.analog{background:#171222;border-radius:10px;padding:10px}.analog strong{display:block}.tester-banner{background:#2b2045;border:1px solid var(--accent2);border-radius:11px;padding:10px;margin-bottom:10px}.page{display:none}.page.active{display:block}.modal{display:none;position:fixed;inset:0;background:rgba(8,6,13,.82);z-index:100;align-items:center;justify-content:center;padding:20px}.modal.show{display:flex}.modal-card{width:min(430px,100%);background:var(--panel);border:1px solid var(--accent2);border-radius:18px;padding:20px;box-shadow:var(--shadow);text-align:center}.modal-card h3{margin-top:0}.footer{text-align:center;color:var(--muted);font-size:.72rem;padding:8px}.hidden{display:none!important}@media(max-width:800px){.status-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.map-grid,.form-grid,.macro-grid{grid-template-columns:1fr}.button-checks,.tester-buttons{grid-template-columns:repeat(2,minmax(0,1fr))}.analog-grid{grid-template-columns:1fr}.map-item{grid-template-columns:90px minmax(0,1fr)}.map-item .listen{grid-column:2}.controller-head,.editor-head{align-items:stretch;flex-direction:column}.controller-head .btn{width:100%}.nav a{font-size:.7rem;padding:8px 2px}.brand img{width:45px}.brand p{display:none}}
</style></head><body><div class="shell"><header class="topbar"><div class="brand"><img src="/assets/logo.png" alt="MiSTer Companion"><div><h1>MiSTer Companion Remote</h1><p>Browser remote v4.0.3</p></div></div><div id="connection" class="pill"><i class="dot"></i><span>Not detected</span></div></header><nav class="nav"><a href="/">Home</a><a href="/controller">Controller</a><a href="/keyboard">Keyboard</a><a href="/games">Games</a><a href="/scripts">Scripts</a><a href="/bluebridge" class="active">BlueBridge</a></nav>
<section id="adapterSelection" class="panel hidden"><label for="adapterSelector">Adapter to manage</label><select id="adapterSelector" onchange="selectAdapter(this.value)"></select></section><main id="overviewPage" class="page active"><section id="controllerCard" class="panel"><div class="controller-head"><div><div class="subtle">Current controller</div><h2 id="currentController">No controller connected</h2><div id="currentState" class="subtle">Turn on a paired controller normally, or start pairing to add one.</div></div><button id="disconnectBtn" class="btn hidden" onclick="disconnectController()">Disconnect</button></div><div class="status-grid"><div class="stat action" onclick="openFirmware()" role="button" tabindex="0"><span>Firmware</span><strong id="firmware">-</strong></div><div class="stat"><span>Bluetooth</span><strong id="bluetooth">-</strong></div><div class="stat"><span>USB output</span><strong id="usbReady">-</strong></div><div class="stat"><span>Battery</span><strong id="battery">-</strong></div><div class="stat"><span>Output</span><select id="outputMode" onchange="outputChanged()"><option value="1">MiSTer</option><option value="2">X-Input</option><option value="3">Generic HID</option><option value="4">Nintendo Switch</option></select></div><div class="stat"><span>Active profile</span><strong id="activeProfile">-</strong></div></div></section><div class="under-card"><button id="pairBtn" class="btn" onclick="pair(true)">Start Pairing</button><button class="btn" onclick="openPaired()">Paired Controllers</button><button id="testerBtn" class="btn hidden" onclick="openTester()">Controller Tester</button><button class="btn" onclick="openFirmware()">Firmware</button></div>
<section id="controllerManagement" class="panel"><div class="toolbar"><div><h2 id="manageTitle">Profiles</h2><div id="manageState" class="subtle">Select a paired controller to manage its profiles.</div></div><button id="closeControllerBtn" class="btn small hidden" onclick="closeManagedController()">Close Controller</button></div><div id="profilePills" class="profile-pills"></div><div id="newProfileRow" class="capture-select"><input id="newProfile" type="text" maxlength="23" placeholder="New profile name"><button class="btn" onclick="createProfile()">Create</button></div><div id="editor" class="hidden"><div class="editor-head"><div><div id="crumb" class="subtle"></div><h2 id="profileTitle"></h2></div><div class="actions"><button id="activateBtn" class="btn small" onclick="activateCurrent()">Activate</button><button class="btn small" onclick="duplicateCurrent()">Duplicate</button><button id="deleteBtn" class="btn small danger" onclick="deleteCurrent()">Delete</button><button class="btn primary" onclick="saveProfile()">Save</button></div></div><div class="tabs"><button class="tab active" data-tab="mapping">Mapping</button><button class="tab" data-tab="analog">Analog</button><button class="tab" data-tab="turbo">Turbo</button><button class="tab" data-tab="macros">Macros</button><button class="tab" data-tab="advanced">Advanced</button></div>
<div id="mapping" class="tabpage active"><div class="surface"><div class="toolbar"><div><h3>Controller mapping</h3><div class="subtle">Choose mappings from the list, or use the controller while it is connected.</div></div><button class="btn small" onclick="resetMapping()">Reset mapping</button><button id="sourceListen" class="btn small" onclick="captureMappingSource()">Press controller button</button></div><div id="mapGrid" class="map-grid"></div></div></div>
<div id="analog" class="tabpage"><div class="surface"><h3>Analog controls</h3><div class="form-grid"><div class="form-group"><label>Left stick deadzone (%)</label><input id="dzL" type="number" min="0" max="50"></div><div class="form-group"><label>Right stick deadzone (%)</label><input id="dzR" type="number" min="0" max="50"></div><div class="form-group"><label>Trigger deadzone (%)</label><input id="dzT" type="number" min="0" max="50"></div></div><div id="invertRows"></div></div></div>
<div id="turbo" class="tabpage"><div class="surface"><div class="switch-row"><div><strong>Turbo</strong><div class="subtle">Turn Turbo on or off without losing its configuration.</div></div><label class="switch"><input id="turboEnabled" type="checkbox"><span class="slider"></span></label></div><div class="form-group"><label>How Turbo is controlled</label><select id="turboMode" onchange="renderTurboHelp()"><option value="0">Button shortcut (modifier + target)</option><option value="1">Dedicated button - press to toggle</option><option value="2">Dedicated button - hold while using Turbo</option></select></div><div id="turboShortcut"><div class="form-group"><label>Shortcut modifier</label><div class="capture-select"><select id="turboModifier"></select><button class="btn small live-only" onclick="captureSelect('turboModifier','Choose Turbo modifier')">Press button</button></div></div><div id="shortcutHelp" class="notice"></div></div><div id="turboDedicated" class="hidden"><div class="form-group"><label>Dedicated Turbo control</label><div class="capture-select"><select id="turboControl"></select><button class="btn small live-only" onclick="captureSelect('turboControl','Choose Turbo control')">Press button</button></div></div></div><div class="form-group"><label>Turbo rate (Hz)</label><input id="turboRate" type="number" min="1" max="30"></div><div class="form-group"><label>Buttons that use Turbo</label><div id="turboButtons" class="button-checks"></div></div></div></div>
<div id="macros" class="tabpage"><div class="surface"><h3>Macros</h3><p class="subtle">Name the macro, choose what it sends, and assign the physical controller button that activates it. Disabling a macro preserves everything.</p><div id="macroList"></div></div></div>
<div id="advanced" class="tabpage"><div class="surface"><h3>Profile</h3><div class="form-group"><label>Profile name</label><input id="profileName" type="text" maxlength="23"></div><div class="notice">Profiles are output-independent. Mapping, analog, Turbo and macros stay with the profile when the global output changes.</div></div><div id="misterSettings" class="surface"><h3>MiSTer mapping</h3><p class="subtle">This identity is only used in MiSTer mode and remains saved when another output is selected.</p><div class="form-group"><label>Mapping identity</label><select id="misterMapping"></select></div><div id="advancedGrid" class="status-grid"></div></div></div>
</div></section></main>
<main id="firmwarePage" class="page"><section class="panel"><div class="toolbar"><div><h3>Adapter name</h3><strong id="adapterName">MC BlueBridge adapter</strong><p id="adapterNameHelp" class="subtle"></p></div><div class="actions"><button id="adapterRenameBtn" class="btn" onclick="renameAdapter()">Rename</button><button id="adapterResetNameBtn" class="btn" onclick="renameAdapter(true)">Reset name</button></div></div></section><section class="panel"><div class="toolbar"><div><h2>Firmware</h2><div class="subtle">Update MC BlueBridge and manage its saved configuration.</div></div><button class="btn" onclick="showPage('overview')">Back</button></div><div class="status-grid"><div class="stat"><span>Installed firmware</span><strong id="firmwareInstalled">-</strong></div><div class="stat"><span>Configuration schema</span><strong id="firmwareSchema">-</strong></div></div></section><section class="panel"><div class="toolbar"><div><h2>Manual Update</h2><div class="subtle">Install MC BlueBridge firmware from a local UF2 file.</div></div></div><div class="firmware-update"><div id="githubFirmware" class="hidden"><div id="githubVersion" class="subtle"></div><button class="btn" onclick="downloadFirmware()">Download &amp; Update</button></div><input id="firmwareFile" type="file" accept=".uf2,application/octet-stream"><div class="form-group"><label for="firmwareConfig">Configuration after update</label><select id="firmwareConfig"><option value="preserve">Preserve Configuration (recommended)</option><option value="reset">Reset Configuration</option></select></div><button id="firmwareUpdateBtn" class="btn primary" onclick="updateFirmware()">Upload &amp; Update</button></div><div id="firmwareUpdateStatus" class="subtle firmware-status">Preserve Configuration keeps BlueBridge controller records, profiles, mappings, macros and settings. Reset Configuration starts BlueBridge with default settings and clears paired controllers.</div></section><section class="panel"><div class="toolbar"><div><h2>Configuration</h2><div class="subtle">Back up, restore or reset the complete BlueBridge configuration.</div></div></div><div class="maintenance-actions"><button class="btn" onclick="exportConfig()">Export Configuration</button><button class="btn" onclick="document.getElementById('importFile').click()">Import Configuration</button><button class="btn danger" onclick="resetConfiguration()">Reset Configuration</button><input id="importFile" type="file" accept=".bbconfig,application/json" hidden></div></section></main>
<main id="pairedPage" class="page"><section class="panel"><div class="toolbar"><div><h2>Paired Controllers</h2><div class="subtle">Manage paired controllers and their stored profiles, even while they are offline.</div></div><button class="btn" onclick="showPage('overview')">Back</button></div><input id="controllerSearch" class="search" type="text" placeholder="Search paired controllers" oninput="renderPaired()"><div id="pairedCount" class="subtle" style="margin-top:9px"></div><div id="pairedList" class="paired-list"></div></section></main>
<main id="testerPage" class="page"><section class="panel"><div class="toolbar"><div><h2>Controller Tester</h2><div id="testerName" class="subtle"></div><label for="testerView">View</label><select id="testerView" onchange="changeTesterView()"><option value="raw">Raw input</option><option value="output">Remapped output</option></select></div><button class="btn" onclick="closeTester()">Done</button></div><div class="tester-banner"><strong>Testing mode is active.</strong><div class="subtle">Controller input is captured by BlueBridge and is not sent to the current USB output.</div></div><div class="status-grid"><div class="stat"><span>Battery</span><strong id="testBattery">-</strong></div><div class="stat"><span>D-Pad</span><strong id="testDpad">Neutral</strong></div><div class="stat"><span>Left trigger</span><strong id="testLT">0</strong></div><div class="stat"><span>Right trigger</span><strong id="testRT">0</strong></div></div><div class="surface" style="margin-top:10px"><h3>Buttons</h3><div id="testerButtons" class="tester-buttons"></div></div><div class="analog-grid"><div class="analog"><span class="subtle">Left stick</span><strong id="testLeft">X 0 / Y 0</strong></div><div class="analog"><span class="subtle">Right stick</span><strong id="testRight">X 0 / Y 0</strong></div><div class="analog"><span class="subtle">Rumble</span><div style="display:flex;gap:7px;margin-top:6px"><select id="rumbleStrength"><option value="64">25%</option><option value="128" selected>50%</option><option value="192">75%</option><option value="255">100%</option></select><button id="rumbleBtn" class="btn small" onclick="testRumble()">Test Rumble</button></div><div id="rumbleStatus" class="subtle" style="margin-top:5px"></div></div></div></section></main>
<div id="captureModal" class="modal"><div class="modal-card"><h3 id="captureTitle">Waiting for controller input</h3><p class="subtle">Press the controller button you want to use. The captured press and release will not be sent to the USB output.</p><button class="btn" onclick="cancelCapture()">Cancel</button></div></div><div class="footer">MC BlueBridge is managed locally through Companion Remote.</div></div><script>
function renderAdapterName() {
  const supported=!!statusData.capabilities?.adapter_rename;
  $('adapterName').textContent=statusData.adapter_name||'MC BlueBridge adapter';
  $('adapterRenameBtn').disabled=!statusData.detected||!supported;
  $('adapterResetNameBtn').disabled=!statusData.detected||!supported||!statusData.adapter_custom_name;
  $('adapterNameHelp').textContent=supported?'The name is saved on this adapter. Changing it reconnects USB.':'Adapter naming requires newer BlueBridge firmware.';
}
async function renameAdapter(reset=false) {
  if(!statusData.capabilities?.adapter_rename)return;
  const name=reset?'':prompt('Adapter name (clear to restore MC BlueBridge adapter)',statusData.adapter_custom_name||'');
  if(name===null)return;
  const clean=name.trim();
  if(new TextEncoder().encode(clean).length>31||/[|\r\n]/.test(clean)){toast('Adapter name must be 31 bytes or fewer and contain no line breaks or |',true);return;}
  try{await post('/api/bluebridge/adapter/rename',{name:clean});await refresh();if(typeof discoverAdapters==='function')await discoverAdapters();renderAdapterName();toast(reset?'Adapter name reset':'Adapter name saved');}catch(e){toast(e.message,true);}
}
let selectedAdapterId='',adapterGeneration=0,adapterBusy=0,adapterActions=0,adapterSwitching=false,adapterDiscovery=null;
const adapterFetch=window.fetch.bind(window);
window.fetch=async(input,options={})=>{
  const url=new URL(typeof input==='string'?input:input.url,location.href);
  if(url.origin!==location.origin||!url.pathname.startsWith('/api/bluebridge/')||url.pathname==='/api/bluebridge/adapters')return adapterFetch(input,options);
  if(!selectedAdapterId)throw new Error('Select an MC BlueBridge adapter');
  const id=selectedAdapterId,generation=adapterGeneration;
  const headers=new Headers(options.headers||(typeof input!=='string'?input.headers:undefined));headers.set('X-BlueBridge-Adapter',id);
  adapterBusy++;if($('adapterSelector'))$('adapterSelector').disabled=true;
  try{const result=await adapterFetch(input,{...options,headers});if(generation!==adapterGeneration)throw new Error('Selected adapter changed');return result;}
  finally{adapterBusy--;$('adapterSelector').disabled=adapterBusy>0||adapterActions>0||adapterSwitching||firmwareUpdating;}
};
async function discoverAdapters() {
  if(adapterDiscovery)return adapterDiscovery;
  adapterDiscovery=(async()=>{
    const response=await adapterFetch('/api/bluebridge/adapters'),data=await response.json();
    if(!response.ok||data.ok===false)throw new Error(data.message||'Unable to discover adapters');
    const adapters=data.adapters||[],selector=$('adapterSelector');
    $('adapterSelection').classList.toggle('hidden',adapters.length<=1&&(!selectedAdapterId||!adapters.length||adapters.some(a=>a.id===selectedAdapterId)));
    if(!selectedAdapterId&&adapters.length)selectedAdapterId=adapters[0].id;
    const seen=new Map();for(const a of adapters)seen.set(a.name,(seen.get(a.name)||0)+1);
    selector.replaceChildren();
    if(selectedAdapterId&&!adapters.some(a=>a.id===selectedAdapterId))selector.append(new Option('Selected adapter disconnected',selectedAdapterId));
    for(const a of adapters){const duplicate=(seen.get(a.name)||0)>1;selector.append(new Option((a.name||'MC BlueBridge adapter')+(duplicate?' · '+a.id.slice(-6):''),a.id));}
    selector.value=selectedAdapterId;selector.disabled=adapterBusy>0||adapterActions>0||adapterSwitching||firmwareUpdating;
    return adapters;
  })();
  try{return await adapterDiscovery;}finally{adapterDiscovery=null;}
}
async function selectAdapter(id) {
  releaseCheckAt=0;
  if(adapterBusy||adapterActions||adapterSwitching||firmwareUpdating){$('adapterSelector').value=selectedAdapterId;return;}
  if(!id||id===selectedAdapterId)return;
  adapterSwitching=true;$('adapterSelector').disabled=true;
  try {
    captureRun++;if(testerTimer){clearInterval(testerTimer);testerTimer=null;}
    $('captureModal').classList.remove('show');
    if(selectedAdapterId){try{await post('/api/bluebridge/capture/stop');}catch(_) {}}
    selectedAdapterId=id;adapterGeneration++;
    statusData={};controllersData={controllers:[]};profilesData=null;profileData=null;currentController=-1;currentProfile=-1;offlineManagement=false;
    $('controllerManagement').classList.add('hidden');$('testerBtn').classList.add('hidden');$('disconnectBtn').classList.add('hidden');$('currentController').textContent='No controller connected';
    showPage('overview');setConnection(false);await refresh();
  }finally{adapterSwitching=false;$('adapterSelector').disabled=adapterBusy>0||adapterActions>0||firmwareUpdating;}
}

function resetMapping(){if(!profileData)return;profileData.map=Array.from({length:26},(_,i)=>i<16?i:22);renderMapping();renderMacros();toast('Default mapping restored. Save to apply.')}async function renameController(index,reset=false){if(!statusData.capabilities?.controller_rename)return;const c=controllerByIndex(index);if(!c)return;const name=reset?'':prompt('Controller name (clear to restore detected name)',c.custom_name||c.name);if(name===null)return;if(new TextEncoder().encode(name.trim()).length>31){toast('Controller name must be 31 bytes or fewer',true);return}try{await post('/api/bluebridge/controllers/rename',{index,name:name.trim()});await refresh();renderPaired();toast(reset?'Controller name reset':'Controller name saved')}catch(e){toast(e.message,true)}}function changeTesterView(){buildTesterButtons();applyTesterCapabilities();updateTester()}function testerOutput(){return $('testerView')?.value==='output'}
const $=id=>document.getElementById(id);let statusData={},controllersData={controllers:[]},profilesData=null,profileData=null,currentController=-1,currentProfile=-1,captureRun=0,testerTimer=null,firmwareUpdating=false,offlineManagement=false,editorDirty=false,profileSaving=false;const sleep=ms=>new Promise(r=>setTimeout(r,ms));async function api(path,opt){const r=await fetch(path,opt);let j;try{j=await r.json()}catch(_){throw new Error(await r.text()||'Invalid response')};if(!r.ok||j.ok===false)throw new Error(j.message||'Request failed');return j}async function post(path,data={}){return api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})}function toast(t,bad=false){let e=document.querySelector('.toast');if(!e){e=document.createElement('div');e.className='notice toast';e.style.cssText='position:fixed;right:18px;bottom:18px;z-index:200;max-width:340px';document.body.append(e)}e.textContent=t;e.style.borderColor=bad?'var(--danger)':'var(--accent2)';clearTimeout(e._t);e._t=setTimeout(()=>e.remove(),2600)}function showPage(name){for(const p of document.querySelectorAll('.page'))p.classList.remove('active');$(name+'Page').classList.add('active')}function controllerByIndex(i){return (controllersData.controllers||[]).find(c=>Number(c.index)===Number(i))}function selectedController(){return controllerByIndex(currentController)}function isSelectedLive(){const c=selectedController();return !!(c&&c.connected)}function labels(){return profilesData&&profilesData.labels?profilesData.labels:Array.from({length:26},(_,i)=>'Button '+(i+1))}function label(i){return labels()[i]||('Button '+(i+1))}function outputLabels(){return labels().slice(0,16)}function capabilities(){return profilesData&&profilesData.capabilities?profilesData.capabilities:{buttons:67108863,dpad:true,left_stick:true,right_stick:true,left_trigger:true,right_trigger:true}}function sourceButtonMask(){let m=Number(capabilities().buttons??67108863);if(isSelectedLive()&&Number(statusData.button_capabilities||0))m&=Number(statusData.button_capabilities);return m}function physicalButtons(){const m=sourceButtonMask();return labels().map((n,i)=>({n,i})).filter(x=>!!(m&(1<<x.i)))}function batteryText(st=statusData){if(!st.battery_supported)return 'Unavailable';const pct=Number(st.battery_percent||0)+'%';if(Number(st.battery_state)===2)return pct+' • Charging';if(Number(st.battery_state)===3)return '100% • Full';return pct}function setConnection(ok){$('connection').classList.toggle('ok',ok);$('connection').querySelector('span').textContent=ok?'BlueBridge connected':'Not detected'}
async function refresh(){try{await discoverAdapters();if(!selectedAdapterId){statusData={};setConnection(false);renderAdapterName();return;}statusData=(await api('/api/bluebridge/status')).status||{};setConnection(!!statusData.detected);renderAdapterName();if(!statusData.detected)return;controllersData=(await api('/api/bluebridge/controllers')).controllers||{controllers:[]};if(currentController<0||!controllerByIndex(currentController))currentController=Number(controllersData.active??controllersData.connected_index??0);await loadProfiles(false);renderAll()}catch(e){if(e.message==='Selected adapter changed')return;setConnection(false);toast(e.message,true)}}
async function loadProfiles(force=true){try{profilesData=(await api('/api/bluebridge/profiles')).profiles||null;if(profilesData){currentController=Number(profilesData.controller_index);if(currentProfile<0||!(profilesData.profiles||[]).some(p=>Number(p.index)===currentProfile))currentProfile=Number(profilesData.active||0);if(force||!profileData||Number(profileData.index)!==currentProfile)profileData=(await api('/api/bluebridge/profile?index='+currentProfile)).profile||null}}catch(e){profilesData=null;profileData=null}}
function renderAll(){renderControllerCard();renderFirmware();renderProfiles();renderPaired();if(profileData&&!editorDirty&&!profileSaving)renderEditor()}
function openFirmware(){showPage('firmware');renderFirmware()}function renderFirmware(){checkFirmwareRelease();if($('firmwareInstalled'))$('firmwareInstalled').textContent=statusData.firmware?'v'+statusData.firmware:'-';if($('firmwareSchema'))$('firmwareSchema').textContent=statusData.config_schema??'-'}
function renderControllerCard(){const connected=controllerByIndex(controllersData.connected_index),managed=offlineManagement?selectedController():null;$('controllerCard').classList.remove('hidden');$('controllerManagement').classList.toggle('hidden',!(connected||managed));$('currentController').textContent=connected?connected.name:'No controller connected';$('currentState').textContent=connected?'Connected and ready for profile management':'Turn on a paired controller normally, or start pairing to add one.';$('disconnectBtn').classList.toggle('hidden',!connected);$('testerBtn').classList.toggle('hidden',!connected);$('pairBtn').classList.toggle('hidden',!!connected);$('firmware').textContent=statusData.firmware||'-';$('bluetooth').textContent=statusData.pairing?'Pairing':(statusData.bt_ready?(connected?'Connected':'Ready'):'Not ready');$('usbReady').textContent=statusData.usb_ready?'Ready':'Not ready';$('battery').textContent=connected?batteryText():'-';$('outputMode').value=String([1,2,3,4].includes(Number(statusData.output_mode))?Number(statusData.output_mode):1);$('activeProfile').textContent=connected?statusData.profile||'-':'-';$('pairBtn').textContent=statusData.pairing?'Stop Pairing':'Start Pairing';$('pairBtn').onclick=()=>pair(!statusData.pairing)}
function renderProfiles(){const c=selectedController();$('closeControllerBtn').classList.toggle('hidden',!(offlineManagement&&c&&!c.connected));$('manageTitle').textContent=c?c.name+' Profiles':'Profiles';$('manageState').textContent=c?(c.connected?'Connected controller':'Paired • Offline — stored settings remain editable'):'Select a paired controller to manage its profiles.';$('profilePills').innerHTML='';for(const p of (profilesData&&profilesData.profiles)||[]){const b=document.createElement('button');b.className='profile-pill'+(Number(p.index)===currentProfile?' active':'');b.textContent=p.name;b.onclick=async()=>{if(profileSaving)return;editorDirty=false;currentProfile=Number(p.index);profileData=(await api('/api/bluebridge/profile?index='+currentProfile)).profile;renderAll()};$('profilePills').append(b)}$('newProfileRow').classList.toggle('hidden',!c);$('editor').classList.toggle('hidden',!profileData)}
function targetOptions(sel,value){sel.innerHTML='';const group=document.createElement('optgroup');group.label='Controller buttons';outputLabels().forEach((n,i)=>{const o=new Option(n,i);group.append(o)});sel.append(group);const mg=document.createElement('optgroup');mg.label='Macros';for(let i=0;i<4;i++){const m=profileData.macros[i]||{};mg.append(new Option((m.name||'Unnamed macro')+(m.enabled?'':' (disabled)'),16+i))}sel.append(mg);const sg=document.createElement('optgroup');sg.label='Special';sg.append(new Option('Turbo control',Number(profileData.turbo_control_mode)===2?21:20));sg.append(new Option('Disabled',22));sel.append(sg);sel.value=String(value)}function buttonSelect(sel,value,allowNone=false){sel.innerHTML='';if(allowNone)sel.append(new Option('Not assigned',255));physicalButtons().forEach(({n,i})=>sel.append(new Option(n,i)));sel.value=String(value)}
function renderEditor(){$('crumb').textContent=(selectedController()?.name||'Controller')+' > '+profileData.name;$('profileTitle').textContent=profileData.name;$('activateBtn').classList.toggle('hidden',!isSelectedLive());$('deleteBtn').disabled=currentProfile===0;for(const e of document.querySelectorAll('.live-only'))e.classList.toggle('hidden',!isSelectedLive());renderMapping();renderAnalog();renderTurbo();renderMacros();renderAdvanced()}
function renderMapping(){const g=$('mapGrid');g.innerHTML='';physicalButtons().forEach(({n,i})=>{const row=document.createElement('div');row.className='map-item';row.dataset.input=i;const l=document.createElement('strong');l.textContent=n;const sel=document.createElement('select');sel.dataset.input=i;targetOptions(sel,profileData.map[i]);sel.onchange=()=>{profileData.map[i]=Number(sel.value);renderMacros()};const listen=document.createElement('button');listen.className='btn small listen live-only';listen.textContent='Press button';listen.onclick=()=>captureMappingDestination(i);if(!isSelectedLive())listen.classList.add('hidden');row.append(l,sel,listen);g.append(row)});$('sourceListen').classList.toggle('hidden',!isSelectedLive())}
function renderAnalog(){$('dzL').value=profileData.deadzone_left;$('dzR').value=profileData.deadzone_right;$('dzT').value=profileData.trigger_deadzone;const caps=capabilities();const inv=$('invertRows');inv.innerHTML='';[['Invert left stick X','invert_x','left_stick'],['Invert left stick Y','invert_y','left_stick'],['Invert right stick X','invert_rx','right_stick'],['Invert right stick Y','invert_ry','right_stick']].filter(x=>caps[x[2]]).forEach(([name,key])=>{const r=document.createElement('div');r.className='switch-row';r.innerHTML='<div><strong>'+name+'</strong></div><label class="switch"><input type="checkbox" '+(profileData[key]?'checked':'')+'><span class="slider"></span></label>';r.querySelector('input').onchange=e=>profileData[key]=e.target.checked;inv.append(r)})}
function makeChecks(root,mask,onchange){root.innerHTML='';physicalButtons().forEach(({n,i})=>{const l=document.createElement('label');l.className='check';const cb=document.createElement('input');cb.type='checkbox';cb.checked=!!(mask&(1<<i));cb.onchange=()=>onchange(i,cb.checked);l.append(cb,document.createTextNode(n));root.append(l)})}function makeOutputChecks(root,mask,onchange){root.innerHTML='';outputLabels().forEach((n,i)=>{const l=document.createElement('label');l.className='check';const cb=document.createElement('input');cb.type='checkbox';cb.checked=!!(mask&(1<<i));cb.onchange=()=>onchange(i,cb.checked);l.append(cb,document.createTextNode(n));root.append(l)})}
function renderTurbo(){$('turboEnabled').checked=!!profileData.turbo_enabled;$('turboMode').value=String(profileData.turbo_control_mode||0);buttonSelect($('turboModifier'),profileData.turbo_modifier??8);buttonSelect($('turboControl'),profileData.turbo_control_button??13);$('turboRate').value=profileData.turbo_rate_hz||12;makeOutputChecks($('turboButtons'),Number(profileData.turbo_mask||0),(i,on)=>{if(on)profileData.turbo_mask|=(1<<i);else profileData.turbo_mask&=~(1<<i)});renderTurboHelp()}function renderTurboHelp(){const mode=Number($('turboMode').value);$('turboShortcut').classList.toggle('hidden',mode!==0);$('turboDedicated').classList.toggle('hidden',mode===0);if(mode===0){const mod=label(Number($('turboModifier').value));$('shortcutHelp').textContent=mod+' + a controller button toggles Turbo for that button. The shortcut itself is consumed and is not sent to the output.'}}
function macroAssignment(m){const target=16+m;for(let i=0;i<(profileData.map||[]).length;i++)if(Number(profileData.map[i])===target)return i;return 255}function renderMacros(){const root=$('macroList');root.innerHTML='';for(let m=0;m<4;m++){const data=profileData.macros[m]||{enabled:false,name:'',output_mask:0};const card=document.createElement('div');card.className='macro-card';card.innerHTML='<div class="macro-head"><input class="macro-name" type="text" maxlength="15" placeholder="Macro name"><label class="switch"><input class="macro-enable" type="checkbox"><span class="slider"></span></label></div><div class="macro-grid"><div class="form-group"><label>Assigned controller button</label><div class="capture-select"><select class="macro-assign"></select><button class="btn small macro-listen live-only">Press button</button></div></div><div class="form-group"><label>Status</label><div class="notice macro-status" style="margin:0"></div></div></div><div class="macro-output"><label class="subtle">Buttons sent by this macro</label><div class="button-checks macro-checks"></div></div>';const name=card.querySelector('.macro-name'),en=card.querySelector('.macro-enable'),assign=card.querySelector('.macro-assign'),listen=card.querySelector('.macro-listen');name.value=data.name||'';en.checked=!!data.enabled;buttonSelect(assign,macroAssignment(m),true);if(!isSelectedLive())listen.classList.add('hidden');name.oninput=()=>data.name=name.value;en.onchange=()=>{data.enabled=en.checked;renderMapping()};assign.onchange=()=>setMacroAssignment(m,Number(assign.value));listen.onclick=()=>captureButton('Assign '+(name.value||'macro'),i=>setMacroAssignment(m,i));card.querySelector('.macro-status').textContent=macroAssignment(m)===255?'Not assigned':('Activated by '+label(macroAssignment(m)));makeOutputChecks(card.querySelector('.macro-checks'),Number(data.output_mask||0),(i,on)=>{if(on)data.output_mask|=(1<<i);else data.output_mask&=~(1<<i)});root.append(card)}}function setMacroAssignment(m,input){for(let i=0;i<profileData.map.length;i++)if(Number(profileData.map[i])===16+m)profileData.map[i]=i<16?i:22;if(input!==255)profileData.map[input]=16+m;renderMapping();renderMacros()}
function renderAdvanced(){$('profileName').value=profileData.name||'';$('outputMode').value=String([1,2,3,4].includes(Number(statusData.output_mode))?Number(statusData.output_mode):1);const misterMode=Number($('outputMode').value)===1;$('misterSettings').classList.toggle('hidden',!misterMode);const sel=$('misterMapping');sel.innerHTML='';sel.append(new Option('Separate MiSTer mapping','separate'));for(const p of profilesData.profiles||[])if(Number(p.index)!==currentProfile)sel.append(new Option('Share MiSTer mapping with '+p.name,'share:'+p.index));sel.value=profileData.mapping_mode==='shared'?'share:'+profileData.shared_with:'separate';const items=[['Controller',selectedController()?.name||'-'],['Native VID','0x'+Number(selectedController()?.native_vid||0).toString(16).padStart(4,'0').toUpperCase()],['Native PID','0x'+Number(selectedController()?.native_pid||0).toString(16).padStart(4,'0').toUpperCase()]];if(misterMode)items.push(['MiSTer virtual PID','0x'+Number(profileData.mister_identity||0).toString(16).padStart(4,'0').toUpperCase()]);const g=$('advancedGrid');g.innerHTML='';items.forEach(([a,b])=>{const d=document.createElement('div');d.className='stat';d.innerHTML='<span>'+a+'</span><strong>'+b+'</strong>';g.append(d)})}async function outputChanged(){const mode=Number($('outputMode').value);try{await post('/api/bluebridge/output',{mode});statusData.output_mode=mode;statusData.output=mode===1?'MiSTer':mode===2?'X-Input':mode===3?'Generic HID':'Nintendo Switch';if(profileData)renderAdvanced();toast('Output changed')}catch(e){$('outputMode').value=String([1,2,3,4].includes(Number(statusData.output_mode))?Number(statusData.output_mode):1);toast(e.message,true)}}
function collectProfileDraft(){const draft=JSON.parse(JSON.stringify(profileData));draft.name=$('profileName').value.trim()||draft.name;for(const sel of $('mapGrid').querySelectorAll('select[data-input]'))draft.map[Number(sel.dataset.input)]=Number(sel.value);for(const [id,key] of [['dzL','deadzone_left'],['dzR','deadzone_right'],['dzT','trigger_deadzone'],['turboRate','turbo_rate_hz'],['turboMode','turbo_control_mode'],['turboControl','turbo_control_button'],['turboModifier','turbo_modifier']])draft[key]=Number($(id).value);draft.turbo_enabled=$('turboEnabled').checked;return draft}
$('editor').addEventListener('input',()=>{editorDirty=true});$('editor').addEventListener('change',()=>{editorDirty=true});
async function saveProfile(){if(profileSaving)return;const idx=currentProfile;const draft=collectProfileDraft();const mv=$('misterMapping').value;const oldName=profileData.name;profileSaving=true;const controls=Array.from($('editor').querySelectorAll('input,select,button')).map(e=>[e,e.disabled]);for(const [e] of controls)e.disabled=true;try{const newName=draft.name;if(newName&&newName!==oldName){await post('/api/bluebridge/profiles/rename',{index:idx,name:newName});draft.name=newName}for(let i=0;i<draft.map.length;i++)await post('/api/bluebridge/profile/map',{profile:idx,input:i,output:Number(draft.map[i])});await post('/api/bluebridge/profile/tuning',{profile:idx,invert_x:!!draft.invert_x,invert_y:!!draft.invert_y,invert_rx:!!draft.invert_rx,invert_ry:!!draft.invert_ry,deadzone_left:draft.deadzone_left,deadzone_right:draft.deadzone_right,trigger_deadzone:draft.trigger_deadzone,turbo_enabled:draft.turbo_enabled,turbo_control_mode:draft.turbo_control_mode,turbo_control_button:draft.turbo_control_button,turbo_rate_hz:draft.turbo_rate_hz,turbo_mask:Number(draft.turbo_mask||0),turbo_modifier:draft.turbo_modifier});for(let m=0;m<4;m++){const d=draft.macros[m];await post('/api/bluebridge/profile/macro',{profile:idx,macro:m,enabled:!!d.enabled,name:d.name||'',output_mask:Number(d.output_mask||0)})}if(mv==='separate')await post('/api/bluebridge/profile/mister-mapping',{profile:idx,mode:'separate'});else await post('/api/bluebridge/profile/mister-mapping',{profile:idx,mode:'share',target:Number(mv.split(':')[1])});profileData=(await api('/api/bluebridge/profile?index='+idx)).profile;editorDirty=false;toast('Profile saved')}catch(e){editorDirty=true;toast(e.message,true)}finally{profileSaving=false;for(const [e,disabled] of controls)e.disabled=disabled;renderAll()}}
async function captureButton(title,onButton){if(!isSelectedLive()){toast('Controller must be connected to listen for input',true);return}const token=++captureRun;$('captureTitle').textContent=title;$('captureModal').classList.add('show');try{await post('/api/bluebridge/capture/start',{mode:'ONCE'});const end=Date.now()+10000;while(token===captureRun&&Date.now()<end){const raw=(await api('/api/bluebridge/capture/status')).capture||{};const c=testerOutput()&&raw.output?{...raw,...raw.output,dpad:[0,1,9,8,10,2,6,4,5][Number(raw.output.hat)||0]||0}:raw;if(c.ready){const i=Number(c.button);await post('/api/bluebridge/capture/stop');$('captureModal').classList.remove('show');captureRun++;onButton(i);return}await sleep(80)}if(token===captureRun){await post('/api/bluebridge/capture/stop');$('captureModal').classList.remove('show');captureRun++;toast('No controller button detected',true)}}catch(e){$('captureModal').classList.remove('show');captureRun++;toast(e.message,true)}}async function cancelCapture(){captureRun++;$('captureModal').classList.remove('show');try{await post('/api/bluebridge/capture/stop')}catch(_){}}function captureMappingSource(){captureButton('Choose the physical button to remap',i=>{const row=document.querySelector('.map-item[data-input="'+i+'"]');if(row){document.querySelectorAll('.map-item').forEach(r=>r.classList.remove('hit'));row.classList.add('hit');row.scrollIntoView({behavior:'smooth',block:'center'});row.querySelector('select').focus()}})}function captureMappingDestination(i){captureButton('Choose output for '+label(i),b=>{if(b>=16){toast('That control is an extended input and cannot be used as a direct output',true);return}profileData.map[i]=b;renderMapping();toast(label(i)+' → '+label(b))})}function captureSelect(id,title){captureButton(title,i=>{$(id).value=i;if(id==='turboModifier')renderTurboHelp();toast(label(i)+' selected')})}
async function pair(start){try{await post('/api/bluebridge/pair',{start});toast(start?'Pairing started':'Pairing stopped');setTimeout(refresh,250)}catch(e){toast(e.message,true)}}async function disconnectController(){if(!confirm('Disconnect this controller? Pairing and profiles will be preserved.'))return;try{await post('/api/bluebridge/controllers/disconnect');offlineManagement=false;$('controllerManagement').classList.add('hidden');$('testerBtn').classList.add('hidden');$('disconnectBtn').classList.add('hidden');$('currentController').textContent='No controller connected';$('currentState').textContent='Turn on a paired controller normally, or start pairing to add one.';toast('Controller disconnected');setTimeout(refresh,450)}catch(e){toast(e.message,true)}}async function createProfile(){const name=$('newProfile').value.trim();if(!name)return;try{await post('/api/bluebridge/profiles/create',{name});$('newProfile').value='';profileData=null;await refresh()}catch(e){toast(e.message,true)}}async function activateCurrent(){try{await post('/api/bluebridge/profiles/select',{index:currentProfile});toast('Profile activated');setTimeout(refresh,300)}catch(e){toast(e.message,true)}}async function duplicateCurrent(){const name=prompt('Name for duplicated profile',(profileData?.name||'Profile')+' Copy');if(!name)return;try{await post('/api/bluebridge/profiles/duplicate',{index:currentProfile,name});profileData=null;await refresh()}catch(e){toast(e.message,true)}}async function deleteCurrent(){if(currentProfile===0||!confirm('Delete this profile?'))return;try{await post('/api/bluebridge/profiles/delete',{index:currentProfile});currentProfile=0;profileData=null;await refresh()}catch(e){toast(e.message,true)}}
async function closeManagedController(){if(profileSaving)return;editorDirty=false;if(!offlineManagement||isSelectedLive())return;try{controllersData=(await api('/api/bluebridge/controllers')).controllers||{controllers:[]};if(isSelectedLive()){renderAll();return}offlineManagement=false;currentController=-1;currentProfile=-1;profilesData=null;profileData=null;$('controllerManagement').classList.add('hidden');const connected=controllerByIndex(controllersData.connected_index);if(connected){await post('/api/bluebridge/controllers/select',{index:connected.index});currentController=Number(connected.index)}await refresh()}catch(e){toast(e.message,true)}}
function openPaired(){offlineManagement=false;showPage('paired');renderPaired()}function renderPaired(){const root=$('pairedList');if(!root)return;root.innerHTML='';const q=($('controllerSearch')?.value||'').toLowerCase();const list=(controllersData.controllers||[]).filter(c=>!q||String(c.name).toLowerCase().includes(q));$('pairedCount').textContent=list.length+' paired controller'+(list.length===1?'':'s');for(const c of list){const r=document.createElement('div');r.className='paired-row'+(c.connected?' connected':'');r.innerHTML='<div><h3></h3><div class="subtle"></div></div><div class="actions"><button class="btn small manage">Manage</button><button class="btn small rename">Rename</button><button class="btn small reset-name">Reset name</button><button class="btn small danger forget">Forget</button></div>';r.querySelector('h3').textContent=c.name;r.querySelector('.subtle').textContent=(c.connected?'Connected':'Offline')+' • '+c.profiles+' profile'+(c.profiles===1?'':'s');r.querySelector('.manage').onclick=()=>manageController(c.index);const rename=r.querySelector('.rename'),reset=r.querySelector('.reset-name');rename.disabled=!statusData.capabilities?.controller_rename;rename.title=rename.disabled?'Update firmware to rename controllers':'';reset.disabled=rename.disabled||!c.custom_name;reset.title=rename.title;rename.onclick=()=>renameController(c.index);reset.onclick=()=>renameController(c.index,true);r.querySelector('.forget').onclick=()=>forgetController(c.index,c.name);root.append(r)}}async function manageController(index){if(profileSaving)return;editorDirty=false;try{const c=controllerByIndex(index);await post('/api/bluebridge/controllers/select',{index});currentController=Number(index);offlineManagement=!!(c&&!c.connected);currentProfile=-1;profileData=null;await loadProfiles(true);showPage('overview');renderAll()}catch(e){toast(e.message,true)}}async function forgetController(index,name){if(!confirm('Forget '+name+' and delete its BlueBridge profiles?'))return;try{await post('/api/bluebridge/controllers/forget',{index});if(currentController===Number(index)){currentController=-1;profileData=null}await refresh();renderPaired()}catch(e){toast(e.message,true)}}
function applyTesterCapabilities(){const c=testerOutput()?{dpad:true,left_trigger:true,right_trigger:true,left_stick:true,right_stick:true}:capabilities();$('testDpad').parentElement.classList.toggle('hidden',!c.dpad);$('testLT').parentElement.classList.toggle('hidden',!c.left_trigger);$('testRT').parentElement.classList.toggle('hidden',!c.right_trigger);$('testLeft').parentElement.classList.toggle('hidden',!c.left_stick);$('testRight').parentElement.classList.toggle('hidden',!c.right_stick)}async function openTester(){const connected=controllerByIndex(controllersData.connected_index);if(!connected)return;try{if(currentController!==Number(connected.index)){await post('/api/bluebridge/controllers/select',{index:connected.index});currentController=Number(connected.index);await loadProfiles(true)}$('testerName').textContent=connected.name;$('testerView').value='raw';$('testerView').querySelector('[value=output]').disabled=!statusData.capabilities?.remapped_tester;$('testerView').title=statusData.capabilities?.remapped_tester?'':'Update firmware to test remapped output';buildTesterButtons();applyTesterCapabilities();showPage('tester');await post('/api/bluebridge/capture/start',{mode:'TESTER'});testerTimer=setInterval(updateTester,90);await updateTester()}catch(e){toast(e.message,true)}}function buildTesterButtons(){const root=$('testerButtons');root.innerHTML='';(testerOutput()?outputLabels().map((n,i)=>({n,i})):physicalButtons()).forEach(({n,i})=>{const d=document.createElement('div');d.className='test-key';d.dataset.button=i;d.textContent=n;root.append(d)})}async function updateTester(){try{const raw=(await api('/api/bluebridge/capture/status')).capture||{};const c=testerOutput()&&raw.output?{...raw,...raw.output,dpad:[0,1,9,8,10,2,6,4,5][Number(raw.output.hat)||0]||0}:raw;if(Number(c.mode||0)===0){clearInterval(testerTimer);testerTimer=null;showPage('overview');await refresh();toast('Controller disconnected');return}for(const e of $('testerButtons').children)e.classList.toggle('on',!!(Number(c.buttons)&(1<<Number(e.dataset.button))));const d=Number(c.dpad||0),ds=[];if(d&1)ds.push('Up');if(d&2)ds.push('Down');if(d&4)ds.push('Left');if(d&8)ds.push('Right');$('testDpad').textContent=ds.join(' + ')||'Neutral';$('testLT').textContent=String(c.lt??0);$('testRT').textContent=String(c.rt??0);$('testLeft').textContent='X '+(c.x??0)+' / Y '+(c.y??0);$('testRight').textContent='X '+(c.rx??0)+' / Y '+(c.ry??0);$('testBattery').textContent=c.battery_supported?(Number(c.battery_percent||0)+'%'):'Unavailable';$('rumbleBtn').disabled=!c.rumble_supported;$('rumbleStatus').textContent=c.rumble_supported?'Rumble supported':'Rumble is not available for this controller'}catch(e){clearInterval(testerTimer);testerTimer=null;toast(e.message,true)}}async function closeTester(){clearInterval(testerTimer);testerTimer=null;try{await post('/api/bluebridge/capture/stop')}catch(_){}showPage('overview');refresh()}async function testRumble(){try{await post('/api/bluebridge/rumble',{strength:Number($('rumbleStrength').value),duration:500});toast('Rumble test started')}catch(e){toast(e.message,true)}}
let releaseCheckAt=0,releaseCheckBusy=false;async function checkFirmwareRelease(){if(releaseCheckBusy||Date.now()<releaseCheckAt)return;releaseCheckBusy=true;releaseCheckAt=Date.now()+60000;try{const j=await api('/api/bluebridge/firmware/releases');const r=j.release||{};$('githubFirmware').classList.toggle('hidden',!r.available);if(r.available){$('githubVersion').textContent='Latest firmware: v'+r.version;$('githubFirmware').querySelector('button').disabled=!r.update_available}}catch(_) {$('githubFirmware').classList.add('hidden')}finally{releaseCheckBusy=false} }
async function downloadFirmware(){if(firmwareUpdating)return;firmwareUpdating=true;try{const j=await post('/api/bluebridge/firmware/download'),info=j.firmware;if(!confirm('Install MC BlueBridge v'+info.version+'? Configuration: '+$('firmwareConfig').value)) {await post('/api/bluebridge/firmware/cancel');return}const result=await post('/api/bluebridge/firmware/install',{configuration:$('firmwareConfig').value});toast(result.firmware.message||'Firmware installed');await refresh();renderFirmware()}catch(e){toast(e.message,true)}finally{firmwareUpdating=false}}
async function updateFirmware(){const input=$('firmwareFile'),file=input.files[0],button=$('firmwareUpdateBtn'),status=$('firmwareUpdateStatus');if(!file){toast('Choose an MC BlueBridge UF2 file first',true);return}if(!/\.uf2$/i.test(file.name)){toast('Choose a .uf2 firmware file',true);return}button.disabled=true;firmwareUpdating=true;status.className='subtle firmware-status busy';status.textContent='Validating firmware…';try{const r=await fetch('/api/bluebridge/firmware/inspect',{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file}),j=await r.json();if(!r.ok||j.ok===false)throw new Error(j.message||'Firmware validation failed');const info=j.firmware||{};if(info.relation==='same'){if(!confirm('Same firmware version detected.\n\nInstalled: v'+info.current_version+'\nUploaded: v'+info.version+'\n\nThis firmware version is already installed. Reinstall it anyway?')){status.className='subtle firmware-status';status.textContent='Firmware update cancelled.';return}}else if(info.relation==='older'){if(!confirm('Older firmware detected.\n\nInstalled: v'+info.current_version+'\nUploaded: v'+info.version+'\n\nSettings created by newer firmware may not be compatible with this version. Install the older version anyway?')){status.className='subtle firmware-status';status.textContent='Firmware update cancelled.';return}}const configuration=$('firmwareConfig').value,label=configuration==='preserve'?'Preserve Configuration':'Reset Configuration';if(!confirm('Ready to update MC BlueBridge.\n\nCurrent firmware: v'+info.current_version+'\nNew firmware: v'+info.version+'\nConfiguration: '+label+'\n\nBlueBridge will restart during the update. Continue?')){status.className='subtle firmware-status';status.textContent='Firmware update cancelled.';return}status.textContent='Installing firmware… BlueBridge will disconnect and restart.';const result=await post('/api/bluebridge/firmware/install',{configuration}),installed=result.firmware||{},state=installed.state||'success';input.value='';profileData=null;if(state==='success'){status.className='subtle firmware-status';status.textContent='Firmware updated successfully: v'+(installed.previous_version||info.current_version)+' → v'+(installed.version||info.version)+'.';toast('MC BlueBridge firmware updated')}else{status.className='subtle firmware-status warning';status.textContent=installed.message||'Firmware was installed, but post-update verification needs attention.';toast('Firmware installed with a warning')}await refresh();renderFirmware()}catch(e){status.className='subtle firmware-status error';status.textContent=e.message;toast(e.message,true)}finally{button.disabled=false;firmwareUpdating=false}}
async function exportConfig(){try{const r=await fetch('/api/bluebridge/config/export');if(!r.ok)throw new Error(await r.text());const b=await r.blob(),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='MC-BlueBridge-Backup.bbconfig';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}catch(e){toast(e.message,true)}}async function resetConfiguration(){if(!confirm('Reset MC BlueBridge configuration?\n\nThis restores default settings and forgets all paired controllers. This cannot be undone unless you exported a backup.'))return;try{await post('/api/bluebridge/config/reset');profileData=null;currentController=-1;currentProfile=-1;toast('BlueBridge configuration reset');await refresh();renderFirmware()}catch(e){toast(e.message,true)}}$('importFile').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{const r=await fetch('/api/bluebridge/config/import',{method:'POST',headers:{'Content-Type':'application/json'},body:await f.text()}),j=await r.json();if(!r.ok||j.ok===false)throw new Error(j.message||'Import failed');toast('Configuration imported');profileData=null;await refresh()}catch(e){toast(e.message,true)}finally{e.target.value=''}};document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.tabpage').forEach(x=>x.classList.remove('active'));b.classList.add('active');$(b.dataset.tab).classList.add('active')});window.addEventListener('beforeunload',()=>{if(testerTimer)navigator.sendBeacon('/api/bluebridge/capture/stop?adapter_id='+encodeURIComponent(selectedAdapterId),'{}')});function guardAdapterAction(work){return async function(...args){adapterActions++;$('adapterSelector').disabled=true;try{return await work.apply(this,args);}finally{adapterActions--;$('adapterSelector').disabled=adapterBusy>0||adapterActions>0||adapterSwitching||firmwareUpdating;}};}
for(const name of ['renameAdapter','renameController','saveProfile','outputChanged','pair','disconnectController','closeManagedController','createProfile','activateCurrent','duplicateCurrent','deleteCurrent','manageController','forgetController','openTester','closeTester','testRumble','captureButton','updateFirmware','downloadFirmware','exportConfig','resetConfiguration'])window[name]=guardAdapterAction(window[name]);
$('importFile').onchange=guardAdapterAction($('importFile').onchange);
refresh();setInterval(()=>{if(document.visibilityState==='visible'&&!profileSaving&&!testerTimer&&!firmwareUpdating&&!$('captureModal').classList.contains('show'))refresh()},4000);
</script></body></html>'''.encode("utf-8")


def send_http(sock, status, content_type, body, extra_headers=None):
    if isinstance(body, str):
        body = body.encode("utf-8")

    # Accepted clients initially use a short timeout for request parsing and
    # WebSocket handshakes. Large binary responses such as MiSTer screenshots
    # can legitimately take longer over Wi-Fi, so do not let that handshake
    # timeout truncate an otherwise valid HTTP response.
    try:
        sock.settimeout(None)
    except Exception:
        pass

    headers = [
        "HTTP/1.1 %s" % status,
        "Content-Type: %s" % content_type,
        "Content-Length: %d" % len(body),
        "Cache-Control: no-store",
        "X-Content-Type-Options: nosniff",
        "Connection: close",
    ]
    if extra_headers:
        headers.extend(extra_headers)

    sock.sendall(("\r\n".join(headers) + "\r\n\r\n").encode("ascii"))
    view = memoryview(body)
    offset = 0
    chunk_size = 64 * 1024
    while offset < len(view):
        end = min(offset + chunk_size, len(view))
        sock.sendall(view[offset:end])
        offset = end



def ioctl_set(fd, request, value):
    fcntl.ioctl(fd, request, int(value))


def input_event(event_type, code, value):
    now = time.time()
    sec = int(now)
    usec = int((now - sec) * 1000000)
    return struct.pack("llHHi", sec, usec, event_type, code, value)


class UInputDevice:
    def __init__(self, name):
        self.name = name
        self.fd = os.open(UINPUT_PATH, os.O_WRONLY | os.O_NONBLOCK)

    def enable_ev(self, code):
        ioctl_set(self.fd, UI_SET_EVBIT, code)

    def enable_key(self, code):
        ioctl_set(self.fd, UI_SET_KEYBIT, code)

    def enable_abs(self, code):
        ioctl_set(self.fd, UI_SET_ABSBIT, code)

    def create(self, vendor, product, abs_ranges=None):
        if abs_ranges is None:
            abs_ranges = {}

        data = bytearray(1116)
        name_bytes = self.name.encode("utf-8")[:79]
        data[0:len(name_bytes)] = name_bytes

        struct.pack_into("HHHH", data, 80, BUS_USB, vendor, product, 1)

        absmax_offset = 92
        absmin_offset = absmax_offset + (64 * 4)

        for code, values in abs_ranges.items():
            min_value, max_value = values
            struct.pack_into("i", data, absmin_offset + code * 4, min_value)
            struct.pack_into("i", data, absmax_offset + code * 4, max_value)

        os.write(self.fd, data)
        fcntl.ioctl(self.fd, UI_DEV_CREATE, 0)
        time.sleep(0.25)

    def emit(self, event_type, code, value):
        os.write(self.fd, input_event(event_type, code, value))
        os.write(self.fd, input_event(EV_SYN, SYN_REPORT, 0))

    def key(self, code, down):
        self.emit(EV_KEY, code, 1 if down else 0)

    def abs(self, code, value):
        self.emit(EV_ABS, code, value)

    def destroy(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY, 0)
        except Exception:
            pass

        try:
            os.close(self.fd)
        except Exception:
            pass


class RemoteState:
    def __init__(self):
        self.keyboard = None
        self.controller = None
        self.lock = threading.RLock()
        self.held_keys = set()
        self.held_buttons = set()

    def init_devices(self):
        self.keyboard = UInputDevice("MiSTer Companion Virtual Keyboard")
        self.keyboard.enable_ev(EV_KEY)

        for code in KEY_CODES.values():
            self.keyboard.enable_key(code)

        self.keyboard.create(0x4D43, 0x0001)

        self.controller = UInputDevice("MiSTer Companion Virtual Controller")
        self.controller.enable_ev(EV_KEY)

        for code in CONTROLLER_BUTTONS.values():
            self.controller.enable_key(code)

        self.controller.create(0x4D43, 0x0002)

    def keyboard_key(self, code, down):
        with self.lock:
            if down:
                self.held_keys.add(code)
            else:
                self.held_keys.discard(code)

            self.keyboard.key(code, down)

    def controller_button(self, code, down):
        with self.lock:
            if down:
                self.held_buttons.add(code)
            else:
                self.held_buttons.discard(code)

            self.controller.key(code, down)

    def set_dpad(self, name, down):
        # MiSTer reliably handles these directions as keyboard navigation keys.
        # The Companion protocol remains controller-based; only the daemon's
        # local uinput translation changes.
        dpad_keys = {
            "up": KEY_CODES["KEY_UP"],
            "down": KEY_CODES["KEY_DOWN"],
            "left": KEY_CODES["KEY_LEFT"],
            "right": KEY_CODES["KEY_RIGHT"],
        }

        if name not in dpad_keys:
            raise ValueError("Unknown D-pad direction: %s" % name)

        self.keyboard_key(dpad_keys[name], down)

    def release_all(self):
        with self.lock:
            for code in list(self.held_keys):
                try:
                    self.keyboard.key(code, False)
                except Exception:
                    pass

            for code in list(self.held_buttons):
                try:
                    self.controller.key(code, False)
                except Exception:
                    pass

            self.held_keys.clear()
            self.held_buttons.clear()


    def destroy(self):
        self.release_all()

        with self.lock:
            if self.keyboard:
                self.keyboard.destroy()
                self.keyboard = None

            if self.controller:
                self.controller.destroy()
                self.controller = None


state = RemoteState()


def normalize_action(action):
    action = (action or "").lower().strip()

    if action == "press":
        return "down"

    if action == "release":
        return "up"

    if action in ("down", "up", "tap"):
        return action

    return ""


def run_action(action, callback):
    action = normalize_action(action)

    if action == "down":
        callback(True)
        return

    if action == "up":
        callback(False)
        return

    if action == "tap":
        callback(True)
        time.sleep(0.045)
        callback(False)
        return

    raise ValueError("Unknown action: %s" % action)



class BlueBridgeManager:
    def __init__(self, adapter_id=None):
        self.lock = threading.RLock()
        self.adapter_id = adapter_id
        self.adapter_name = "MC BlueBridge adapter"
        self.verified = False
        self.path = None
        self.fd = None
        self.rx = b""
        self.counter = 0
        self.info = {}

    def _read_text(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()
        except Exception:
            return ""

    def _usb_info(self, tty_path):
        name = os.path.basename(tty_path)
        node = os.path.realpath("/sys/class/tty/%s/device" % name)
        info = {"path": tty_path, "product": "", "manufacturer": "", "serial": "", "vendor": "", "product_id": ""}
        seen = set()
        while node and node not in seen and node != "/":
            seen.add(node)
            if not info["product"]:
                info["product"] = self._read_text(os.path.join(node, "product"))
            if not info["manufacturer"]:
                info["manufacturer"] = self._read_text(os.path.join(node, "manufacturer"))
            if not info["serial"]:
                info["serial"] = self._read_text(os.path.join(node, "serial"))
            if not info["vendor"]:
                info["vendor"] = self._read_text(os.path.join(node, "idVendor"))
                if info["vendor"]:
                    info["usb_path"] = node
            if not info["product_id"]:
                info["product_id"] = self._read_text(os.path.join(node, "idProduct"))
            node = os.path.dirname(node)
        return info

    @staticmethod
    def identity(info):
        return info.get("serial") or "usb:" + os.path.basename(info.get("usb_path", info["path"]))

    def discover_all(self):
        found = []
        candidates = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
        for path in candidates:
            info = self._usb_info(path)
            try:
                vid = int(info.get("vendor", ""), 16)
                pid = int(info.get("product_id", ""), 16)
            except ValueError:
                continue
            if (vid == 0x2e8a and (pid in (0x10b1, 0x10b2) or 0xb000 <= pid <= 0xbfff)) or (vid == 0x0f0d and pid == 0x0092):
                found.append((path, info))
        return found

    def discover(self):
        for path, info in self.discover_all():
            if self.adapter_id is None or self.identity(info) == self.adapter_id:
                return path, info
        return None, {}

    @property
    def firmware_upload(self):
        suffix = hashlib.sha256(str(self.adapter_id).encode("utf-8")).hexdigest()[:16]
        return BLUEBRIDGE_FIRMWARE_UPLOAD.replace(".uf2", "-" + suffix + ".uf2")

    @property
    def pre_update_backup(self):
        suffix = hashlib.sha256(str(self.adapter_id).encode("utf-8")).hexdigest()[:16]
        return BLUEBRIDGE_PRE_UPDATE_BACKUP.replace(".bbconfig", "-" + suffix + ".bbconfig")

    def _configure(self, fd):
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] = termios.CLOCAL | termios.CREAD | termios.CS8
        attrs[3] = 0
        attrs[4] = termios.B115200
        attrs[5] = termios.B115200
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIOFLUSH)

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except Exception:
                pass
        self.fd = None
        self.path = None
        self.rx = b""
        self.info = {}

    def connect(self):
        path, info = self.discover()
        if not path:
            self.close()
            raise RuntimeError("MC BlueBridge not detected")
        if self.fd is not None and self.path == path:
            return
        self.close()
        fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self._configure(fd)
        self.fd = fd
        self.path = path
        self.info = info
        self.rx = b""
        time.sleep(0.05)
        try:
            hello = self.request_json("HELLO")
            if hello.get("protocol") != 2 or hello.get("hardware") != "Pico 2 W" or not str(hello.get("firmware_id", "")).startswith("MCBLUEBRIDGE|"):
                raise RuntimeError("The selected device is not an MC BlueBridge adapter")
            if hello.get("adapter_id") and hello["adapter_id"] != self.adapter_id:
                raise RuntimeError("BlueBridge adapter identity changed")
            self.verified = True
            self.adapter_name = hello.get("adapter_name") or "MC BlueBridge adapter"
        except Exception:
            self.close()
            raise

    def _next_id(self):
        self.counter = (self.counter + 1) & 0x7fffffff
        if self.counter == 0:
            self.counter = 1
        return str(self.counter)

    def _write(self, data):
        raw = data.encode("utf-8")
        offset = 0
        while offset < len(raw):
            try:
                n = os.write(self.fd, raw[offset:])
            except BlockingIOError:
                n = 0
            if n:
                offset += n
            else:
                select.select([], [self.fd], [], 0.1)

    def _readline(self, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            pos = self.rx.find(b"\n")
            if pos >= 0:
                raw = self.rx[:pos]
                self.rx = self.rx[pos + 1:]
                return raw.decode("utf-8", errors="replace").rstrip("\r")
            remaining = max(0.0, end - time.monotonic())
            ready, _, _ = select.select([self.fd], [], [], min(0.15, remaining))
            if not ready:
                continue
            try:
                chunk = os.read(self.fd, 4096)
            except BlockingIOError:
                chunk = b""
            if chunk:
                self.rx += chunk
            else:
                time.sleep(0.01)
        raise TimeoutError("BlueBridge did not respond")

    def _send(self, command, *args):
        self.connect()
        request_id = self._next_id()
        fields = ["BB1", request_id, command]
        fields.extend(str(x).replace("\r", " ").replace("\n", " ") for x in args)
        self._write("|".join(fields) + "\n")
        return request_id

    def _parse_line(self, line):
        parts = line.split("|", 3)
        if len(parts) < 3 or parts[0] != "BB1":
            return None
        return parts[1], parts[2], parts[3] if len(parts) > 3 else ""

    def request(self, command, *args, timeout=2.5):
        with self.lock:
            try:
                request_id = self._send(command, *args)
                end = time.monotonic() + timeout
                while time.monotonic() < end:
                    parsed = self._parse_line(self._readline(max(0.05, end - time.monotonic())))
                    if not parsed or parsed[0] != request_id:
                        continue
                    _, status, payload = parsed
                    if status == "ERR":
                        raise RuntimeError(payload or "BlueBridge command failed")
                    if status != "OK":
                        raise RuntimeError("Unexpected BlueBridge response")
                    return payload
                raise TimeoutError("BlueBridge did not respond")
            except Exception:
                self.close()
                raise

    def request_json(self, command, *args, timeout=2.5):
        payload = self.request(command, *args, timeout=timeout)
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except Exception:
            return {"value": payload}

    def status(self):
        try:
            hello = self.request_json("HELLO")
            status = self.request_json("STATUS")
            status["detected"] = True
            status["port"] = self.path
            status["serial"] = self.info.get("serial", "")
            status["usb_product"] = self.info.get("product", "")
            status["protocol"] = hello.get("protocol", status.get("protocol"))
            status["config_schema"] = hello.get("config_schema")
            status["capabilities"] = hello.get("capabilities", {})
            self.adapter_name = hello.get("adapter_name") or "MC BlueBridge adapter"
            status["adapter_id"] = self.adapter_id
            status["adapter_name"] = self.adapter_name
            status["adapter_custom_name"] = hello.get("adapter_custom_name", "")
            return status
        except Exception as e:
            return {"detected": False, "connected": False, "message": str(e)}

    def controllers(self):
        return self.request_json("CONTROLLERS")

    def profiles(self):
        return self.request_json("PROFILES")

    def profile(self, index):
        return self.request_json("PROFILE_GET", int(index))

    def export_config(self):
        with self.lock:
            try:
                request_id = self._send("CONFIG_EXPORT")
                schema = None
                size = None
                checksum = None
                chunks = {}
                end = time.monotonic() + 8.0
                while time.monotonic() < end:
                    parsed = self._parse_line(self._readline(max(0.05, end - time.monotonic())))
                    if not parsed or parsed[0] != request_id:
                        continue
                    _, status, payload = parsed
                    if status == "ERR":
                        raise RuntimeError(payload or "BlueBridge export failed")
                    if status == "DATA_BEGIN":
                        fields = payload.split("|")
                        if len(fields) != 3:
                            raise RuntimeError("Invalid BlueBridge export header")
                        schema = int(fields[0])
                        size = int(fields[1])
                        checksum = int(fields[2])
                    elif status == "DATA":
                        fields = payload.split("|", 1)
                        if len(fields) != 2:
                            raise RuntimeError("Invalid BlueBridge export chunk")
                        chunks[int(fields[0])] = fields[1]
                    elif status == "DATA_END":
                        break
                if schema is None or size is None or checksum is None:
                    raise RuntimeError("Incomplete BlueBridge export")
                data = bytearray(size)
                written = 0
                for offset in sorted(chunks):
                    raw = bytes.fromhex(chunks[offset])
                    end_offset = offset + len(raw)
                    if offset != written or end_offset > size:
                        raise RuntimeError("Invalid BlueBridge export data")
                    data[offset:end_offset] = raw
                    written = end_offset
                if written != size:
                    raise RuntimeError("Incomplete BlueBridge export data")
                return {
                    "format": "MC-BLUEBRIDGE-CONFIG-1",
                    "schema": schema,
                    "size": size,
                    "checksum": checksum,
                    "data": base64.b64encode(bytes(data)).decode("ascii"),
                }
            except Exception:
                self.close()
                raise

    def import_config(self, package):
        if str(package.get("format", "")) != "MC-BLUEBRIDGE-CONFIG-1":
            raise ValueError("Unsupported BlueBridge configuration file")
        schema = int(package.get("schema", 0))
        size = int(package.get("size", 0))
        checksum = int(package.get("checksum", 0))
        try:
            data = base64.b64decode(str(package.get("data", "")), validate=True)
        except Exception:
            raise ValueError("Invalid BlueBridge configuration data")
        if len(data) != size:
            raise ValueError("BlueBridge configuration size does not match")
        self.request("CONFIG_IMPORT_BEGIN", schema, size, checksum, timeout=3.0)
        chunk_size = 128
        for offset in range(0, len(data), chunk_size):
            self.request("CONFIG_IMPORT_CHUNK", offset, data[offset:offset + chunk_size].hex().upper(), timeout=3.0)
        self.request("CONFIG_IMPORT_COMMIT", timeout=4.0)
        return True


class BlueBridgeRegistry:
    def __init__(self):
        self.lock = threading.RLock()
        self.managers = {}
        self.scanner = BlueBridgeManager()

    def inventory(self):
        with self.lock:
            present = {}
            for path, info in self.scanner.discover_all():
                adapter_id = BlueBridgeManager.identity(info)
                if adapter_id in present:
                    continue
                manager = self.managers.get(adapter_id)
                if manager is None:
                    manager = BlueBridgeManager(adapter_id)
                    self.managers[adapter_id] = manager
                if not manager.verified and not manager.status().get("detected"):
                    continue
                present[adapter_id] = (manager, info)
            return present

    def adapters(self):
        return [{"id": key, "name": manager.adapter_name, "serial": info.get("serial", ""), "port": info["path"]} for key, (manager, info) in self.inventory().items()]

    def resolve(self, adapter_id):
        present = self.inventory()
        with self.lock:
            if adapter_id:
                manager = self.managers.get(adapter_id)
                if manager is None or not manager.verified:
                    raise RuntimeError("Selected MC BlueBridge adapter is not available")
                return manager
            if len(present) != 1:
                raise RuntimeError("Select an MC BlueBridge adapter" if present else "MC BlueBridge not detected")
            return next(iter(present.values()))[0]

    def close(self):
        with self.lock:
            for manager in self.managers.values():
                with manager.lock:
                    manager.close()


bluebridge_registry = BlueBridgeRegistry()

BLUEBRIDGE_FIRMWARE_UPLOAD = "/media/fat/Scripts/.config/companion_remote/bluebridge_update.uf2"
BLUEBRIDGE_PRE_UPDATE_BACKUP = "/media/fat/Scripts/.config/companion_remote/MC-BlueBridge-Pre-Update.bbconfig"
BLUEBRIDGE_UF2_FAMILIES = {0xE48BFF57, 0xE48BFF59, 0xE48BFF5B}
BLUEBRIDGE_UF2_CODE_FAMILIES = {0xE48BFF59, 0xE48BFF5B}

import urllib.request
import urllib.error
import json
import re
import time
import threading

BLUEBRIDGE_RELEASE_URL = "https://api.github.com/repos/Anime0t4ku/MC-BlueBridge/releases"

def version_key(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?", str(value).strip())
    if not match:
        raise ValueError("Invalid firmware version: " + str(value))
    pre = match.group(4)
    if pre:
        pre = re.sub(r"^beta-(\d+)$", r"beta.\1", pre)
    identifiers = tuple((0, int(p)) if p.isdigit() else (1, p) for p in (pre or "").split("."))
    return tuple(int(match.group(i)) for i in (1, 2, 3)) + (1 if pre is None else 0, identifiers)

def _lookup_bluebridge_release(installed="", opener=None):
    opener = opener or urllib.request.urlopen
    candidates = []
    stable_only = bool(installed and version_key(installed)[3])
    try:
        for page in range(1, 21):
            request = urllib.request.Request(BLUEBRIDGE_RELEASE_URL + "?per_page=100&page=" + str(page), headers={"User-Agent": "MiSTer-Companion-BlueBridge", "Accept": "application/vnd.github+json"})
            with opener(request, timeout=15) as response:
                releases = json.load(response)
            if not isinstance(releases, list):
                return {"available": False}
            for release in releases:
                if release.get("draft"):
                    continue
                try:
                    key = version_key(release.get("tag_name", ""))
                except ValueError:
                    continue
                if stable_only and (not key[3] or release.get("prerelease")):
                    continue
                for asset in release.get("assets", []):
                    url = asset.get("browser_download_url", "")
                    if asset.get("name") == "mc_bluebridge.uf2" and url.startswith("https://github.com/Anime0t4ku/MC-BlueBridge/releases/download/") and 0 < int(asset.get("size", 0)) <= 8 * 1024 * 1024:
                        candidates.append((key, release, asset))
                        break
            if len(releases) < 100:
                break
    except (OSError, ValueError, urllib.error.URLError):
        return {"available": False}
    if not candidates:
        return {"available": False}
    stable = [c for c in candidates if c[0][3] and not c[1].get("prerelease")]
    key, release, asset = max((stable or candidates) if not installed else candidates, key=lambda c: c[0])
    return {"available": True, "version": release["tag_name"].lstrip("v"), "url": asset["browser_download_url"], "size": asset["size"], "update_available": not installed or key > version_key(installed)}

def download_bluebridge_release(info):
    if not info.get("available") or not info.get("url", "").startswith("https://github.com/Anime0t4ku/MC-BlueBridge/releases/download/"):
        raise ValueError("No firmware release available")
    request = urllib.request.Request(info["url"], headers={"User-Agent": "MiSTer-Companion-BlueBridge"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(8 * 1024 * 1024 + 1)
    if not data or len(data) > 8 * 1024 * 1024 or len(data) != info["size"]:
        raise ValueError("Incomplete or oversized firmware download")
    return data

_release_cache = {}
_release_cache_lock = threading.RLock()

def bluebridge_release(installed="", opener=None):
    if opener is not None:
        return _lookup_bluebridge_release(installed, opener)
    with _release_cache_lock:
        entry = _release_cache.get(installed)
        if entry and time.monotonic() < entry[0]:
            return dict(entry[1])
        info = _lookup_bluebridge_release(installed)
        _release_cache[installed] = (time.monotonic() + (300 if info.get("available") else 60), info)
        return dict(info)

def _version_tuple(value):
    return version_key(value)

def _uf2_info(data):
    if not data or len(data) % 512:
        raise ValueError("Invalid UF2 file size")
    chunks = []
    families = set()
    seen_blocks = set()
    block_groups = {}
    for offset in range(0, len(data), 512):
        block = data[offset:offset + 512]
        magic0, magic1, flags, target, payload_size, block_no, num_blocks, family = struct.unpack_from("<IIIIIIII", block, 0)
        magic_end = struct.unpack_from("<I", block, 508)[0]
        if magic0 != 0x0A324655 or magic1 != 0x9E5D5157 or magic_end != 0x0AB16F30:
            raise ValueError("Invalid UF2 block")
        if payload_size == 0 or payload_size > 476:
            raise ValueError("Invalid UF2 payload")
        family_id = family if flags & 0x00002000 else 0
        key = (family_id, num_blocks, block_no)
        if key in seen_blocks:
            raise ValueError("Duplicate UF2 block")
        seen_blocks.add(key)
        if not num_blocks or block_no >= num_blocks:
            raise ValueError("Invalid UF2 block sequence")
        compatibility_block = (
            offset == 0 and family_id == 0xE48BFF57 and
            flags in (0x00002000, 0x0000A000) and payload_size == 256 and
            block_no == 0 and num_blocks == 2 and
            0x10000000 <= target < 0x12000000 and target % 256 == 0 and
            block[32:288] == b'\xef' * 256 and
            (not flags & 0x00008000 or struct.unpack_from("<I", block, 288)[0] == 0x9957E304)
        )
        if compatibility_block:
            continue
        block_groups.setdefault((family_id, num_blocks), set()).add(block_no)
        if family_id:
            families.add(family_id)
            if family_id not in BLUEBRIDGE_UF2_FAMILIES:
                raise ValueError("This UF2 contains blocks for an unsupported device family")
        if family_id in BLUEBRIDGE_UF2_FAMILIES:
            chunks.append((target, block[32:32 + payload_size]))
    if not block_groups:
        raise ValueError("UF2 contains no firmware blocks")
    firmware_blocks = sum(len(numbers) for numbers in block_groups.values())
    complete_per_family = all(len(numbers) == count for (_, count), numbers in block_groups.items())
    counts = {count for _, count in block_groups}
    global_numbers = {number for numbers in block_groups.values() for number in numbers}
    complete_global = len(counts) == 1 and next(iter(counts)) == firmware_blocks and len(global_numbers) == firmware_blocks
    if not complete_per_family and not complete_global:
        raise ValueError("Incomplete UF2 block sequence")
    if not families.intersection(BLUEBRIDGE_UF2_CODE_FAMILIES):
        raise ValueError("This UF2 is not for MC BlueBridge on Raspberry Pi Pico 2 W")
    image = b"".join(payload for _, payload in sorted(chunks, key=lambda item: item[0]))
    match = re.search(rb"MCBLUEBRIDGE\|([0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?)\|PICO2W\|SCHEMA=([0-9]+)", image)
    version = None
    schema = None
    if match:
        version = match.group(1).decode("ascii")
        schema = int(match.group(2))
    elif b"MC BlueBridge" in image:
        versions = [x.decode("ascii") for x in re.findall(rb"(?<![0-9])[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?![0-9])", image)]
        if versions:
            version = max(versions, key=_version_tuple)
    if not version:
        raise ValueError("Unable to identify this file as MC BlueBridge firmware")
    return {"version": version, "config_schema": schema, "family": "RP2350", "size": len(data)}

def _inspect_bluebridge_firmware(data, bluebridge):
    info = _uf2_info(data)
    current = bluebridge.status()
    if not current.get("detected"):
        raise RuntimeError("MC BlueBridge not detected")
    current_version = str(current.get("firmware", "0.0.0"))
    a = _version_tuple(info["version"])
    b = _version_tuple(current_version)
    relation = "newer" if a > b else "same" if a == b else "older"
    info["current_version"] = current_version
    info["relation"] = relation
    return info

def _find_rp2350_device(usb_path):
    if not usb_path:
        raise RuntimeError("Unable to identify the selected adapter USB port")
    for node in sorted(glob.glob("/sys/class/block/*")):
        device_path = os.path.realpath(os.path.join(node, "device"))
        if not device_path.startswith(usb_path + "/"):
            continue
        device = "/dev/" + os.path.basename(node)
        try:
            label = subprocess.check_output(["blkid", "-s", "LABEL", "-o", "value", device], stderr=subprocess.DEVNULL, text=True).strip()
            if label == "RP2350":
                return device
        except Exception:
            pass
    return None

def _mounted_path(device):
    real = os.path.realpath(device)
    try:
        with open("/proc/mounts", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                fields = line.split()
                if len(fields) >= 2 and os.path.realpath(fields[0]) == real:
                    return fields[1], False
    except Exception:
        pass
    mountpoint = "/tmp/mc_bluebridge_rp2350_" + os.path.basename(real)
    os.makedirs(mountpoint, exist_ok=True)
    result = subprocess.run(["mount", device, mountpoint], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "Unable to mount RP2350 update volume").strip())
    return mountpoint, True

def _wait_for_bluebridge(bluebridge, timeout=60.0, stable_reads=3):
    end = time.monotonic() + timeout
    last = None
    stable = 0
    latest = None
    while time.monotonic() < end:
        try:
            status = bluebridge.status()
            if status.get("detected"):
                latest = status
                stable += 1
                if stable >= stable_reads:
                    return latest
            else:
                stable = 0
                last = status.get("message")
        except Exception as e:
            stable = 0
            last = str(e)
        time.sleep(0.75)
    return None

def _retry_bluebridge_action(bluebridge, action, timeout=15.0):
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        try:
            return action()
        except Exception as e:
            last = str(e)
            bluebridge.close()
            time.sleep(1.0)
    raise RuntimeError(last or "BlueBridge did not respond")

def _reset_bluebridge_configuration(bluebridge):
    _retry_bluebridge_action(bluebridge, lambda: bluebridge.request("FORGET_ALL", timeout=4.0))
    try:
        bluebridge.request("CONFIG_RESET", timeout=2.0)
    except Exception:
        pass
    try:
        bluebridge.request("PAIR_STOP", timeout=2.0)
    except Exception:
        pass
    bluebridge.close()
    status = _wait_for_bluebridge(bluebridge, timeout=30.0, stable_reads=2)
    if status is None:
        raise RuntimeError("BlueBridge did not return after configuration reset")
    controllers = _retry_bluebridge_action(bluebridge, lambda: bluebridge.controllers(), timeout=10.0)
    if controllers.get("controllers"):
        raise RuntimeError("BlueBridge returned, but stored controllers are still present")
    return status

def _install_bluebridge_firmware(bluebridge, settings_mode):
    if settings_mode not in ("preserve", "reset"):
        raise ValueError("Invalid configuration option")
    with open(bluebridge.firmware_upload, "rb") as f:
        data = f.read()
    info = _inspect_bluebridge_firmware(data, bluebridge)
    if settings_mode == "preserve":
        backup = bluebridge.export_config()
        os.makedirs(os.path.dirname(bluebridge.pre_update_backup), exist_ok=True)
        with open(bluebridge.pre_update_backup, "w", encoding="utf-8") as f:
            json.dump(backup, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
    usb_path = bluebridge.info.get("usb_path")
    if not usb_path:
        raise RuntimeError("Unable to identify the selected adapter USB port")
    bluebridge.request("REBOOT_BOOTSEL", timeout=3.0)
    bluebridge.close()
    device = None
    end = time.monotonic() + 12.0
    while time.monotonic() < end and not device:
        device = _find_rp2350_device(usb_path)
        if not device:
            time.sleep(0.25)
    if not device:
        raise RuntimeError("RP2350 update mode was not detected")
    mountpoint, mounted_here = _mounted_path(device)
    try:
        target = os.path.join(mountpoint, "MC-BlueBridge.uf2")
        with open(bluebridge.firmware_upload, "rb") as src, open(target, "wb", buffering=0) as dst:
            shutil.copyfileobj(src, dst, 65536)
            os.fsync(dst.fileno())
        try:
            os.sync()
        except Exception:
            pass
    finally:
        if mounted_here:
            time.sleep(0.5)
            subprocess.run(["umount", mountpoint], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    status = _wait_for_bluebridge(bluebridge)
    result = {"version": info["version"], "previous_version": info["current_version"], "configuration": settings_mode, "state": "success", "message": "Firmware updated successfully"}
    if status is None:
        result["state"] = "verification_timeout"
        result["message"] = "Firmware was transferred successfully, but BlueBridge did not return in time for verification. Refresh this page after BlueBridge reconnects."
    elif _version_tuple(status.get("firmware", "0.0.0")) != _version_tuple(info["version"]):
        result["state"] = "verification_warning"
        result["message"] = "Firmware was transferred, but BlueBridge reported v%s instead of v%s." % (status.get("firmware", "unknown"), info["version"])
    else:
        if settings_mode == "reset":
            try:
                _reset_bluebridge_configuration(bluebridge)
                result["message"] = "Firmware updated successfully and configuration reset"
            except Exception as e:
                result["state"] = "configuration_warning"
                result["message"] = "Firmware v%s is installed, but the requested configuration step could not be confirmed: %s" % (info["version"], str(e))
    try:
        os.unlink(bluebridge.firmware_upload)
    except Exception:
        pass
    return result

def response(ok=True, response_type="result", message="", version=DAEMON_VERSION, **extra):
    result = {
        "ok": ok,
        "type": response_type,
        "message": message,
        "version": version,
    }
    result.update(extra)
    return result


def handle_command(command):
    command_type = str(command.get("type", "")).lower().strip()

    if command_type in ("ping", "status"):
        return response(True, "status", "MiSTer Companion Remote daemon is running")

    if command_type == "system":
        system_command = str(command.get("command", "")).lower().strip()

        if system_command in ("release_all", "release-all"):
            state.release_all()
            return response(True, "system", "Released all inputs")

        if system_command in ("soft_reboot", "soft-reboot", "return_home", "return-home"):
            state.release_all()

            def return_home():
                time.sleep(0.20)
                os.system('sync; echo "load_core /media/fat/menu.rbf" > /dev/MiSTer_cmd')

            threading.Thread(target=return_home, daemon=True).start()
            return response(True, "system", "Returning to MiSTer Home")

        if system_command in ("cold_reboot", "cold-reboot", "reboot"):
            state.release_all()

            def cold_reboot():
                time.sleep(0.35)
                subprocess.Popen(
                    "sync; /sbin/reboot >/dev/null 2>&1",
                    shell=True,
                    close_fds=True,
                )

            threading.Thread(target=cold_reboot, daemon=True).start()
            return response(True, "system", "Cold reboot requested")

        return response(False, "error", "Unknown system command")

    if command_type in ("screenshot", "screen"):
        png = capture_screenshot()
        return response(True, "screenshot", "Screenshot captured", url="/api/screenshot", bytes=len(png))

    if command_type in ("games", "game"):
        action = str(command.get("action", "")).lower().strip()
        if action in ("systems", "list_systems", "list-systems"):
            return response(True, "games", "OK", systems=list_systems())
        if action in ("list", "browse", "search"):
            system = str(command.get("system", "")).strip()
            query = str(command.get("query", "") or command.get("q", "")).strip()
            return response(True, "games", "OK", games=list_games(system, query))
        if action in ("launch", "start"):
            system = str(command.get("system", "")).strip()
            path = str(command.get("path", "")).strip()
            target = launch_game(system, path)
            return response(True, "games", "Launch requested", system=system, path=path, target=target)
        return response(False, "error", "Unknown game action")

    if command_type in ("scripts", "script"):
        action = str(command.get("action", "")).lower().strip()
        if action in ("list", "browse"):
            return response(True, "scripts", "OK", scripts=list_scripts(), status=script_status())
        if action in ("status", "active"):
            return response(True, "scripts", "OK", status=script_status())
        if action in ("launch", "start", "run"):
            info = launch_script(command.get("path", ""))
            return response(True, "scripts", "Script launched", status=info)
        if action in ("stop", "kill"):
            stopped = stop_script()
            return response(True, "scripts", "Script stopped" if stopped else "No script was running", status=script_status())
        if action in ("console", "open_console", "open-console"):
            return response(True, "scripts", "Script console opened", status=open_script_console())
        if action in ("close_console", "close-console"):
            return response(True, "scripts", "Returned from script console", status=close_script_console())
        return response(False, "error", "Unknown script action")

    if command_type == "keyboard":
        key = str(command.get("key", "")).upper().strip()
        action = command.get("action", "")

        if key not in KEY_CODES:
            return response(False, "error", "Unknown keyboard key: %s" % key)

        run_action(action, lambda down: state.keyboard_key(KEY_CODES[key], down))
        return response(True, "keyboard", "OK")

    if command_type == "controller":
        control = str(command.get("control", "")).lower().strip()
        name = str(command.get("name", "") or command.get("button", "")).lower().strip()
        action = command.get("action", "")

        if control == "dpad" or name in ("up", "down", "left", "right"):
            run_action(action, lambda down: state.set_dpad(name, down))
            return response(True, "controller", "OK")

        if name not in CONTROLLER_BUTTONS:
            return response(False, "error", "Unknown controller button: %s" % name)

        run_action(action, lambda down: state.controller_button(CONTROLLER_BUTTONS[name], down))
        return response(True, "controller", "OK")

    return response(False, "error", "Unknown command type: %s" % command_type)


def read_exact(sock, size):
    data = b""

    while len(data) < size:
        chunk = sock.recv(size - len(data))

        if not chunk:
            raise ConnectionError("socket closed")

        data += chunk

    return data


def read_ws_frame(sock):
    header = read_exact(sock, 2)
    b1, b2 = header[0], header[1]

    opcode = b1 & 0x0F
    masked = b2 & 0x80
    length = b2 & 0x7F

    if length == 126:
        length = struct.unpack(">H", read_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", read_exact(sock, 8))[0]

    mask = b""

    if masked:
        mask = read_exact(sock, 4)

    payload = read_exact(sock, length) if length else b""

    if masked:
        payload = bytes(payload[i] ^ mask[i % 4] for i in range(len(payload)))

    return opcode, payload


def send_ws_frame(sock, payload):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")

    header = bytearray()
    header.append(0x81)

    length = len(payload)

    if length < 126:
        header.append(length)
    elif length <= 65535:
        header.append(126)
        header.extend(struct.pack(">H", length))
    else:
        header.append(127)
        header.extend(struct.pack(">Q", length))

    sock.sendall(bytes(header) + payload)


def send_json(sock, payload):
    send_ws_frame(sock, json.dumps(payload))


def websocket_accept(key):
    value = key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    digest = hashlib.sha1(value.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def _read_http_request(sock):
    data = b""
    while b"\r\n\r\n" not in data and len(data) < 131072:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    head, sep, body = data.partition(b"\r\n\r\n")
    text = head.decode("iso-8859-1", errors="ignore")
    lines = text.split("\r\n")
    if not lines or len(lines[0].split()) < 2:
        return "", "", {}, b""
    first = lines[0].split()
    method, target = first[0].upper(), first[1]
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.lower().strip()] = value.strip()
    try:
        content_length = int(headers.get("content-length", "0"))
    except Exception:
        content_length = 0
    while len(body) < content_length:
        chunk = sock.recv(min(4096, content_length - len(body)))
        if not chunk:
            break
        body += chunk
    return method, target, headers, body[:content_length]


def _json_http(sock, payload, status="200 OK"):
    send_http(sock, status, "application/json; charset=utf-8", json.dumps(payload).encode("utf-8"))


def handle_client(sock, address, path):
    try:
        method, target, headers, request_body = _read_http_request(sock)
        if not target:
            return
        parsed = urllib.parse.urlsplit(target)
        request_path = parsed.path
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

        if request_path == "/status":
            _json_http(sock, response(True, "status", "MiSTer Companion Remote daemon is running"))
            return
        if request_path in ("/", "/index.html"):
            send_http(sock, "200 OK", "text/html; charset=utf-8", HOME_HTML)
            return
        if request_path in ("/controller", "/controller/"):
            send_http(sock, "200 OK", "text/html; charset=utf-8", CONTROLLER_HTML)
            return
        if request_path in ("/keyboard", "/keyboard/"):
            send_http(sock, "200 OK", "text/html; charset=utf-8", KEYBOARD_HTML)
            return
        if request_path in ("/games", "/games/"):
            send_http(sock, "200 OK", "text/html; charset=utf-8", GAMES_HTML)
            return
        if request_path in ("/scripts", "/scripts/"):
            send_http(sock, "200 OK", "text/html; charset=utf-8", SCRIPTS_HTML)
            return
        if request_path in ("/bluebridge", "/bluebridge/"):
            send_http(sock, "200 OK", "text/html; charset=utf-8", BLUEBRIDGE_HTML)
            return
        if request_path == "/assets/logo.png" or request_path == "/favicon.ico":
            send_http(sock, "200 OK", "image/png", LOGO_PNG, ["Cache-Control: public, max-age=86400"])
            return

        if request_path == "/api/bluebridge/adapters":
            try:
                _json_http(sock, response(True, "bluebridge", "OK", adapters=bluebridge_registry.adapters()))
            except Exception as e:
                _json_http(sock, response(False, "error", str(e)), "503 Service Unavailable")
            return
        if request_path.startswith("/api/bluebridge/"):
            try:
                bluebridge = bluebridge_registry.resolve(headers.get("x-bluebridge-adapter", "") or query.get("adapter_id", [""])[0])
            except Exception as e:
                if request_path == "/api/bluebridge/status":
                    _json_http(sock, response(True, "bluebridge", "OK", status={"detected": False, "connected": False, "message": str(e)}))
                else:
                    _json_http(sock, response(False, "error", str(e)), "503 Service Unavailable")
                return
            with bluebridge.lock:
                if request_path == "/api/bluebridge/adapter/rename":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        if not bluebridge.request_json("HELLO").get("capabilities", {}).get("adapter_rename"):
                            raise RuntimeError("Adapter naming requires newer BlueBridge firmware")
                        name = str(payload.get("name", "")).strip()
                        if len(name.encode("utf-8")) > 31 or any(c in name for c in ("|", "\r", "\n")):
                            raise ValueError("Adapter name must be 31 bytes or fewer and contain no line breaks or |")
                        bluebridge.request("ADAPTER_RENAME", name)
                        bluebridge.adapter_name = name or "MC BlueBridge adapter"
                        bluebridge.close()
                        _json_http(sock, response(True, "bluebridge", "Adapter name saved"))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/status":
                    _json_http(sock, response(True, "bluebridge", "OK", status=bluebridge.status()))
                    return
                if request_path == "/api/bluebridge/firmware/releases":
                    try:
                        info = bluebridge_release(bluebridge.status().get("firmware", ""))
                        _json_http(sock, response(True, "bluebridge", "OK", release=info))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/firmware/download":
                    try:
                        if method != "POST":
                            raise ValueError("POST required")
                        info = bluebridge_release(bluebridge.status().get("firmware", ""))
                        data = download_bluebridge_release(info)
                        firmware = _inspect_bluebridge_firmware(data, bluebridge)
                        if version_key(firmware["version"]) != version_key(info["version"]):
                            raise ValueError("Firmware does not match release tag")
                        os.makedirs(os.path.dirname(bluebridge.firmware_upload), exist_ok=True)
                        with open(bluebridge.firmware_upload, "wb") as f:
                            f.write(data)
                            f.flush()
                            os.fsync(f.fileno())
                        _json_http(sock, response(True, "bluebridge", "Firmware validated", firmware=firmware))
                    except Exception as e:
                        try:
                            os.unlink(bluebridge.firmware_upload)
                        except OSError:
                            pass
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/firmware/inspect":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        if not request_body or len(request_body) > 8 * 1024 * 1024:
                            raise ValueError("Firmware file is empty or too large")
                        info = _inspect_bluebridge_firmware(request_body, bluebridge)
                        os.makedirs(os.path.dirname(bluebridge.firmware_upload), exist_ok=True)
                        with open(bluebridge.firmware_upload, "wb") as f:
                            f.write(request_body)
                            f.flush()
                            os.fsync(f.fileno())
                        _json_http(sock, response(True, "bluebridge", "Firmware validated", firmware=info))
                    except Exception as e:
                        try:
                            os.unlink(bluebridge.firmware_upload)
                        except Exception:
                            pass
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/firmware/install":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        result = _install_bluebridge_firmware(bluebridge, str(payload.get("configuration", "preserve")))
                        _json_http(sock, response(True, "bluebridge", "Firmware updated", firmware=result))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/firmware/cancel":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        os.unlink(bluebridge.firmware_upload)
                    except Exception:
                        pass
                    _json_http(sock, response(True, "bluebridge", "Firmware update cancelled"))
                    return
                if request_path == "/api/bluebridge/controllers":
                    try:
                        _json_http(sock, response(True, "bluebridge", "OK", controllers=bluebridge.controllers()))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "503 Service Unavailable")
                    return
                if request_path == "/api/bluebridge/controllers/rename":
                    try:
                        if method != "POST":
                            raise ValueError("POST required")
                        if not bluebridge.request_json("HELLO").get("capabilities", {}).get("controller_rename"):
                            raise ValueError("Update firmware to rename controllers")
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        name = str(payload.get("name", "")).strip()
                        if len(name.encode("utf-8")) > 31:
                            raise ValueError("Controller name must be 31 bytes or fewer")
                        name = name.replace("|", " ").replace("\r", " ").replace("\n", " ")
                        bluebridge.request("CONTROLLER_RENAME", int(payload.get("index", -1)), name)
                        _json_http(sock, response(True, "bluebridge", "Controller renamed"))
                    except Exception as e:
                        _json_http(sock, response(False, "bluebridge", str(e)), "400 Bad Request")
                    return

                if request_path == "/api/bluebridge/controllers/select":
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        bluebridge.request("CONTROLLER_SELECT", int(payload.get("index", -1)))
                        _json_http(sock, response(True, "bluebridge", "Controller selected"))
                    except Exception as e:
                        _json_http(sock, response(False, "bluebridge", str(e)), "400 Bad Request")
                    return

                if request_path == "/api/bluebridge/capture/start":
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        mode = str(payload.get("mode", "ONCE")).upper()
                        bluebridge.request("CAPTURE_START", "TESTER" if mode == "TESTER" else "ONCE")
                        _json_http(sock, response(True, "bluebridge", "Capture started"))
                    except Exception as e:
                        _json_http(sock, response(False, "bluebridge", str(e)), "400 Bad Request")
                    return

                if request_path == "/api/bluebridge/capture/status":
                    try:
                        _json_http(sock, response(True, "bluebridge", "OK", capture=bluebridge.request_json("CAPTURE_STATUS")))
                    except Exception as e:
                        _json_http(sock, response(False, "bluebridge", str(e)), "400 Bad Request")
                    return

                if request_path == "/api/bluebridge/capture/stop":
                    try:
                        bluebridge.request("CAPTURE_STOP")
                        _json_http(sock, response(True, "bluebridge", "Capture stopped"))
                    except Exception as e:
                        _json_http(sock, response(False, "bluebridge", str(e)), "400 Bad Request")
                    return

                if request_path == "/api/bluebridge/rumble":
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        strength = max(0, min(255, int(payload.get("strength", 128))))
                        duration = max(50, min(3000, int(payload.get("duration", 500))))
                        bluebridge.request("CONTROLLER_RUMBLE", strength, duration)
                        _json_http(sock, response(True, "bluebridge", "Rumble started"))
                    except Exception as e:
                        _json_http(sock, response(False, "bluebridge", str(e)), "400 Bad Request")
                    return

                if request_path == "/api/bluebridge/controllers/disconnect":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        bluebridge.request("CONTROLLER_DISCONNECT")
                        _json_http(sock, response(True, "bluebridge", "Controller disconnect requested"))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/controllers/forget":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        bluebridge.request("CONTROLLER_FORGET", int(payload.get("index", -1)))
                        _json_http(sock, response(True, "bluebridge", "Controller forgotten"))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/profiles":
                    try:
                        _json_http(sock, response(True, "bluebridge", "OK", profiles=bluebridge.profiles()))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "503 Service Unavailable")
                    return
                if request_path == "/api/bluebridge/profile":
                    try:
                        index = int(query.get("index", ["0"])[0])
                        _json_http(sock, response(True, "bluebridge", "OK", profile=bluebridge.profile(index)))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/pair":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        bluebridge.request("PAIR_START" if payload.get("start", True) else "PAIR_STOP")
                        _json_http(sock, response(True, "bluebridge", "OK", status=bluebridge.status()))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "503 Service Unavailable")
                    return
                if request_path == "/api/bluebridge/forget":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        bluebridge.request("FORGET_ALL")
                        _json_http(sock, response(True, "bluebridge", "Paired controllers cleared"))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "503 Service Unavailable")
                    return
                if request_path == "/api/bluebridge/profiles/create":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        name = str(payload.get("name", "")).strip()
                        if not re.fullmatch(r"[A-Za-z0-9 _.-]{1,23}", name):
                            raise ValueError("Invalid profile name")
                        result = bluebridge.request_json("PROFILE_CREATE", name)
                        _json_http(sock, response(True, "bluebridge", "Profile created", result=result))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/profiles/duplicate":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        name = str(payload.get("name", "Copy")).strip()
                        if not re.fullmatch(r"[A-Za-z0-9 _.-]{1,23}", name):
                            raise ValueError("Invalid profile name")
                        result = bluebridge.request_json("PROFILE_DUPLICATE", int(payload.get("index", -1)), name)
                        _json_http(sock, response(True, "bluebridge", "Profile duplicated", result=result))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/profiles/select":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        bluebridge.request("PROFILE_SELECT", int(payload.get("index", -1)))
                        bluebridge.close()
                        _json_http(sock, response(True, "bluebridge", "Profile activated"))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/profiles/delete":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        bluebridge.request("PROFILE_DELETE", int(payload.get("index", -1)))
                        _json_http(sock, response(True, "bluebridge", "Profile deleted"))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/profiles/rename":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        name = str(payload.get("name", "")).strip()
                        if not re.fullmatch(r"[A-Za-z0-9 _.-]{1,23}", name):
                            raise ValueError("Invalid profile name")
                        bluebridge.request("PROFILE_RENAME", int(payload.get("index", -1)), name)
                        _json_http(sock, response(True, "bluebridge", "Profile renamed"))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/profile/map":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        bluebridge.request("PROFILE_MAP", int(payload.get("profile", -1)), int(payload.get("input", -1)), int(payload.get("output", -1)))
                        _json_http(sock, response(True, "bluebridge", "Mapping updated"))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/profile/tuning":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        profile_index = int(payload.get("profile", -1))
                        bluebridge.request("PROFILE_TUNE", profile_index, int(bool(payload.get("invert_x"))), int(bool(payload.get("invert_y"))), int(bool(payload.get("invert_rx"))), int(bool(payload.get("invert_ry"))), int(payload.get("deadzone_left", 8)), int(payload.get("deadzone_right", 8)), int(payload.get("trigger_deadzone", 4)), int(payload.get("turbo_rate_hz", 12)), int(payload.get("turbo_mask", 0)))
                        bluebridge.request("PROFILE_TURBO_MODIFIER", profile_index, int(payload.get("turbo_modifier", 8)))
                        bluebridge.request("PROFILE_TURBO_CONTROL", profile_index, int(bool(payload.get("turbo_enabled"))), int(payload.get("turbo_control_mode", 0)), int(payload.get("turbo_control_button", 13)))
                        _json_http(sock, response(True, "bluebridge", "Profile tuning updated"))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/profile/macro":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        bluebridge.request("PROFILE_MACRO", int(payload.get("profile", -1)), int(payload.get("macro", -1)), int(bool(payload.get("enabled"))), str(payload.get("name", "")).replace("|", " ").replace("\r", " ").replace("\n", " ")[:15], int(payload.get("output_mask", 0)))
                        _json_http(sock, response(True, "bluebridge", "Macro updated"))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/profile/mister-mapping":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        profile = int(payload.get("profile", -1))
                        mode = str(payload.get("mode", "separate")).lower().strip()
                        if mode == "separate":
                            bluebridge.request("PROFILE_MAPPING_SEPARATE", profile)
                        elif mode == "share":
                            bluebridge.request("PROFILE_MAPPING_SHARE", profile, int(payload.get("target", -1)))
                        else:
                            raise ValueError("Invalid MiSTer mapping mode")
                        bluebridge.close()
                        _json_http(sock, response(True, "bluebridge", "MiSTer mapping updated"))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/profile/identity":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        payload = json.loads(request_body.decode("utf-8") or "{}")
                        profile = int(payload.get("profile", -1))
                        if payload.get("unique", True):
                            bluebridge.request("PROFILE_MAPPING_SEPARATE", profile)
                        else:
                            bluebridge.request("PROFILE_MAPPING_SHARE", profile, 0)
                        bluebridge.close()
                        _json_http(sock, response(True, "bluebridge", "MiSTer mapping updated"))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/output":
                    try:
                        if method == "POST":
                            payload = json.loads(request_body.decode("utf-8") or "{}")
                            bluebridge.request("OUTPUT_SET", int(payload.get("mode", 1)))
                        _json_http(sock, response(True, "bluebridge", "OK", output=bluebridge.request_json("OUTPUT_GET")))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return
                if request_path == "/api/bluebridge/config/reset":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        _reset_bluebridge_configuration(bluebridge)
                        _json_http(sock, response(True, "bluebridge", "Configuration reset"))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "503 Service Unavailable")
                    return
                if request_path == "/api/bluebridge/config/export":
                    try:
                        package = bluebridge.export_config()
                        body = json.dumps(package, indent=2).encode("utf-8")
                        send_http(sock, "200 OK", "application/json; charset=utf-8", body, ["Content-Disposition: attachment; filename=MC-BlueBridge-Backup.bbconfig"])
                    except Exception as e:
                        send_http(sock, "503 Service Unavailable", "text/plain; charset=utf-8", str(e).encode("utf-8"))
                    return
                if request_path == "/api/bluebridge/config/import":
                    if method != "POST":
                        _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                        return
                    try:
                        package = json.loads(request_body.decode("utf-8") or "{}")
                        bluebridge.import_config(package)
                        _json_http(sock, response(True, "bluebridge", "Configuration imported"))
                    except Exception as e:
                        _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
                    return

        if request_path == "/api/scripts/list":
            try:
                _json_http(sock, response(True, "scripts", "OK", scripts=list_scripts(), status=script_status()))
            except Exception as e:
                _json_http(sock, response(False, "error", "Unable to list scripts: %s" % e), "500 Internal Server Error")
            return
        if request_path == "/api/scripts/status":
            _json_http(sock, response(True, "scripts", "OK", status=script_status()))
            return
        if request_path == "/api/scripts/launch":
            if method != "POST":
                _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                return
            try:
                payload = json.loads(request_body.decode("utf-8") or "{}")
                info = launch_script(payload.get("path", ""))
                _json_http(sock, response(True, "scripts", "Script launched", status=info))
            except Exception as e:
                _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
            return
        if request_path == "/api/scripts/stop":
            if method != "POST":
                _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                return
            try:
                stopped = stop_script()
                _json_http(sock, response(True, "scripts", "Script stopped" if stopped else "No script was running", status=script_status()))
            except Exception as e:
                _json_http(sock, response(False, "error", str(e)), "500 Internal Server Error")
            return
        if request_path == "/api/scripts/console":
            if method != "POST":
                _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                return
            try:
                _json_http(sock, response(True, "scripts", "Script console opened", status=open_script_console()))
            except Exception as e:
                _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
            return

        if request_path == "/api/games/systems":
            try:
                _json_http(sock, response(True, "games", "OK", systems=list_systems()))
            except Exception as e:
                _json_http(sock, response(False, "error", "Unable to list systems: %s" % e), "500 Internal Server Error")
            return
        if request_path == "/api/games/list":
            try:
                system = query.get("system", ["All"])[0] or "All"
                q = query.get("q", [""])[0]
                refresh = query.get("refresh", ["0"])[0].lower() in ("1", "true", "yes")
                offset = query.get("offset", ["0"])[0]
                limit = query.get("limit", ["200"])[0]
                page, total, has_more = list_games_page(system, q, offset=offset, limit=limit, refresh=refresh)
                _json_http(sock, response(True, "games", "OK", games=page, total=total, offset=max(0, int(offset or 0)), has_more=has_more))
            except Exception as e:
                _json_http(sock, response(False, "error", "Unable to list games: %s" % e), "500 Internal Server Error")
            return
        if request_path == "/api/games/launch":
            if method != "POST":
                _json_http(sock, response(False, "error", "POST required"), "405 Method Not Allowed")
                return
            try:
                payload = json.loads(request_body.decode("utf-8") or "{}")
                system = str(payload.get("system", "")).strip()
                game_path = str(payload.get("path", "")).strip()
                launch_target = launch_game(system, game_path)
                _json_http(sock, response(True, "games", "Launch requested", system=system, path=game_path, target=launch_target))
            except Exception as e:
                _json_http(sock, response(False, "error", str(e)), "400 Bad Request")
            return
        if request_path == "/api/artwork":
            system = query.get("system", [""])[0]
            game_path = query.get("path", [""])[0]
            art = artwork_for_game(system, game_path)
            if not art:
                send_http(sock, "404 Not Found", "text/plain; charset=utf-8", b"Artwork not found")
                return
            try:
                with open(art, "rb") as f:
                    body = f.read()
                send_http(sock, "200 OK", "image/jpeg", body, ["Cache-Control: public, max-age=3600"])
            except Exception as e:
                send_http(sock, "500 Internal Server Error", "text/plain; charset=utf-8", str(e).encode("utf-8"))
            return
        if request_path == "/api/screenshot":
            try:
                fresh = query.get("fresh", ["0"])[0].lower() in ("1", "true", "yes")
                if fresh:
                    body = capture_screenshot()
                else:
                    body = _read_png(latest_screenshot_path())
                send_http(sock, "200 OK", "image/png", body, ["Cache-Control: no-store"])
            except Exception as e:
                send_http(sock, "500 Internal Server Error", "text/plain; charset=utf-8", str(e).encode("utf-8"))
            return

        if request_path != path:
            send_http(sock, "404 Not Found", "text/plain; charset=utf-8", b"Not found")
            return

        ws_key = headers.get("sec-websocket-key")
        if not ws_key:
            sock.sendall(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            return
        accept = websocket_accept(ws_key)
        response_headers = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Accept: %s\r\n"
            "\r\n"
        ) % accept
        sock.sendall(response_headers.encode("ascii"))
        try:
            sock.settimeout(None)
        except Exception:
            pass
        send_json(sock, response(True, "hello", "MiSTer Companion Remote daemon connected"))
        while running:
            opcode, payload = read_ws_frame(sock)
            if opcode == 0x8:
                break
            if opcode == 0x9:
                sock.sendall(bytes([0x8A, len(payload)]) + payload)
                continue
            if opcode != 0x1:
                continue
            try:
                command = json.loads(payload.decode("utf-8"))
                result = handle_command(command)
            except Exception as e:
                result = response(False, "error", str(e))
            send_json(sock, result)
    except Exception as e:
        try:
            print("Client %s disconnected: %s" % (address, e), flush=True)
        except Exception:
            pass
    finally:
        try:
            state.release_all()
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass


def signal_handler(_signum, _frame):
    global running
    running = False

    try:
        stop_script()
    except Exception:
        pass

    try:
        bluebridge_registry.close()
    except Exception:
        pass

    try:
        state.release_all()
    except Exception:
        pass

    try:
        state.destroy()
    except Exception:
        pass

    sys.exit(0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default="9191")
    parser.add_argument("--path", default="/remote/v1")
    parser.add_argument("--version", action="version", version=DAEMON_VERSION)
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    state.init_devices()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, int(args.port)))
    server.listen(5)

    print("MiSTer Companion Remote daemon listening on ws://%s:%s%s" % (args.host, args.port, args.path), flush=True)

    try:
        while running:
            try:
                client, address = server.accept()
            except OSError:
                if not running:
                    break
                continue

            try:
                client.settimeout(10)
            except Exception:
                pass

            thread = threading.Thread(
                target=handle_client,
                args=(client, address, args.path),
                daemon=True,
            )
            thread.start()
    finally:
        try:
            server.close()
        except Exception:
            pass

        state.destroy()


if __name__ == "__main__":
    main()
PYEOF

    # Stamp the generated daemon with the shell script version so a replaced
    # companion_remote.sh can detect and refresh an older daemon automatically.
    if command -v sed >/dev/null 2>&1; then
        sed -i "s/__COMPANION_REMOTE_VERSION__/$SCRIPT_VERSION/g" "$DAEMON" 2>/dev/null
    fi

    chmod +x "$DAEMON" 2>/dev/null
}

script_installed() {
    [ -f "$SCRIPT_PATH" ]
}

daemon_installed() {
    [ -f "$DAEMON" ]
}

installed_daemon_version() {
    if ! daemon_installed; then
        return 1
    fi

    "$DAEMON" --version 2>/dev/null | head -n 1
}

daemon_needs_refresh() {
    if ! daemon_installed; then
        return 0
    fi

    _daemon_version="$(installed_daemon_version)"

    if [ -z "$_daemon_version" ]; then
        return 0
    fi

    [ "$_daemon_version" != "$SCRIPT_VERSION" ]
}

pid_value() {
    if [ -f "$PID" ]; then
        cat "$PID" 2>/dev/null | head -n 1
    fi
}

process_running_by_pid() {
    _pid="$1"

    case "$_pid" in
        ''|*[!0-9]*|0) return 1 ;;
    esac

    if ! kill -0 "$_pid" 2>/dev/null; then
        return 1
    fi

    if [ ! -r "/proc/$_pid/cmdline" ]; then
        return 1
    fi

    tr '\000' '\n' < "/proc/$_pid/cmdline" 2>/dev/null | grep -F -x "$DAEMON" >/dev/null 2>&1
}

daemon_running() {
    _pid="$(pid_value)"

    if process_running_by_pid "$_pid"; then
        return 0
    fi

    rm -f "$PID" 2>/dev/null

    if command -v pgrep >/dev/null 2>&1; then
        if pgrep -f "$DAEMON" >/dev/null 2>&1; then
            return 0
        fi
    fi

    ps | grep "$DAEMON" | grep -v grep >/dev/null 2>&1
}

port_listening() {
    if command -v netstat >/dev/null 2>&1; then
        netstat -lnt 2>/dev/null | grep -q ":$PORT "
        return $?
    fi

    if command -v ss >/dev/null 2>&1; then
        ss -lnt 2>/dev/null | grep -q ":$PORT "
        return $?
    fi

    return 1
}

startup_enabled() {
    if [ ! -f "$STARTUP" ]; then
        return 1
    fi

    grep -F "# MiSTer Companion Remote BEGIN" "$STARTUP" >/dev/null 2>&1
}

remove_startup_block() {
    if [ ! -f "$STARTUP" ]; then
        return 0
    fi

    _tmp="$STARTUP.tmp.$$"

    awk '
        BEGIN { skip = 0 }

        /^# MiSTer Companion Remote BEGIN$/ {
            skip = 1
            next
        }

        /^# MiSTer Companion Remote END$/ {
            skip = 0
            next
        }

        /^# MiSTer Companion Remote$/ {
            skip = 1
            next
        }

        skip == 1 && /^fi$/ {
            skip = 0
            next
        }

        skip == 1 {
            next
        }

        /companion_remote.sh start --unattended/ {
            next
        }

        /companion_remote_daemon/ {
            next
        }

        {
            print
        }
    ' "$STARTUP" > "$_tmp" 2>/dev/null

    if [ -f "$_tmp" ]; then
        mv "$_tmp" "$STARTUP"
        chmod +x "$STARTUP" 2>/dev/null
        return 0
    fi

    rm -f "$_tmp" 2>/dev/null
    return 1
}

print_status() {
    if script_installed; then
        SCRIPT_INSTALLED=1
    else
        SCRIPT_INSTALLED=0
    fi

    if [ -d "$BASE" ]; then
        BASE_EXISTS=1
    else
        BASE_EXISTS=0
    fi

    if [ -f "$CONFIG" ]; then
        CONFIG_EXISTS=1
    else
        CONFIG_EXISTS=0
    fi

    if daemon_installed; then
        DAEMON_INSTALLED=1
    else
        DAEMON_INSTALLED=0
    fi

    if daemon_running; then
        DAEMON_RUNNING=1
    else
        DAEMON_RUNNING=0
    fi

    if port_listening; then
        PORT_LISTENING=1
    else
        PORT_LISTENING=0
    fi

    if startup_enabled; then
        START_ON_BOOT=1
    else
        START_ON_BOOT=0
    fi

    INSTALLED_DAEMON_VERSION="$(installed_daemon_version 2>/dev/null)"
    if [ -z "$INSTALLED_DAEMON_VERSION" ]; then
        INSTALLED_DAEMON_VERSION="unknown"
    fi

    if daemon_needs_refresh; then
        DAEMON_UPDATE_REQUIRED=1
    else
        DAEMON_UPDATE_REQUIRED=0
    fi

    print_line "SCRIPT_INSTALLED=$SCRIPT_INSTALLED"
    print_line "VERSION=$SCRIPT_VERSION"
    print_line "BASE_EXISTS=$BASE_EXISTS"
    print_line "CONFIG_EXISTS=$CONFIG_EXISTS"
    print_line "DAEMON_INSTALLED=$DAEMON_INSTALLED"
    print_line "DAEMON_VERSION=$INSTALLED_DAEMON_VERSION"
    print_line "DAEMON_UPDATE_REQUIRED=$DAEMON_UPDATE_REQUIRED"
    print_line "DAEMON_RUNNING=$DAEMON_RUNNING"
    print_line "PORT_LISTENING=$PORT_LISTENING"
    print_line "START_ON_BOOT=$START_ON_BOOT"
    print_line "HOST=$HOST"
    print_line "PORT=$PORT"
    print_line "WS_PATH=$WS_PATH"
    print_line "SCRIPT_PATH=$SCRIPT_PATH"
    print_line "BASE=$BASE"
    print_line "DAEMON=$DAEMON"
    print_line "CONFIG=$CONFIG"
    print_line "LOG=$LOG"
    print_line "PID=$PID"
}

status_text() {
    if daemon_installed; then
        DAEMON_INSTALLED_TEXT="Installed"
    else
        DAEMON_INSTALLED_TEXT="Missing"
    fi

    if daemon_running; then
        DAEMON_RUNNING_TEXT="Running"
    else
        DAEMON_RUNNING_TEXT="Stopped"
    fi

    if port_listening; then
        PORT_TEXT="Listening"
    else
        PORT_TEXT="Not listening"
    fi

    if startup_enabled; then
        BOOT_TEXT="Enabled"
    else
        BOOT_TEXT="Disabled"
    fi

    cat <<EOF
Version: $SCRIPT_VERSION
Daemon version: $(installed_daemon_version 2>/dev/null || echo unknown)
Status: $DAEMON_RUNNING_TEXT
Daemon: $DAEMON_INSTALLED_TEXT
Boot: $BOOT_TEXT
Port $PORT: $PORT_TEXT
EOF
}

full_status_text() {
    cat <<EOF
$(status_text)

Web Remote:
http://<MiSTer IP>:$PORT/

WebSocket:
ws://<MiSTer IP>:$PORT$WS_PATH

Script:
$SCRIPT_PATH

Config:
$CONFIG

Log:
$LOG
EOF
}

print_status_human() {
    print_line "Status"
    print_line "------"
    full_status_text
}

install_manager() {
    ensure_base
    write_default_config
    create_daemon_file

    log_line "Install requested."

    if daemon_installed; then
        chmod +x "$DAEMON" 2>/dev/null
        log_line "Daemon file created."
        print_line "OK: Daemon manager installed. Daemon file created."
        return 0
    fi

    log_line "Daemon file could not be created."
    print_line "ERROR: Daemon file could not be created:"
    print_line "$DAEMON"
    return 1
}

stop_daemon() {
    log_line "Stop requested."

    _pid="$(pid_value)"

    if process_running_by_pid "$_pid"; then
        kill "$_pid" 2>/dev/null
        sleep 1

        if process_running_by_pid "$_pid"; then
            kill -9 "$_pid" 2>/dev/null
            sleep 1
        fi
    fi

    if command -v pkill >/dev/null 2>&1; then
        pkill -f "$DAEMON" 2>/dev/null
    fi

    rm -f "$PID" 2>/dev/null

    if daemon_running; then
        print_line "ERROR: Daemon still appears to be running."
        log_line "Stop failed. Daemon still appears to be running."
        return 1
    fi

    print_line "OK: Daemon stopped."
    log_line "Daemon stopped."
    return 0
}

start_daemon() {
    ensure_base
    write_default_config
    log_line "Start requested."

    if daemon_running; then
        if daemon_needs_refresh; then
            _old_version="$(installed_daemon_version 2>/dev/null)"
            [ -n "$_old_version" ] || _old_version="unknown"
            print_line "INFO: Updating daemon from $_old_version to $SCRIPT_VERSION."
            log_line "Running daemon is outdated ($_old_version). Refreshing to $SCRIPT_VERSION."
            stop_daemon >/dev/null 2>&1
        else
            print_line "OK: Daemon already running."
            log_line "Daemon already running."
            return 0
        fi
    fi

    if daemon_needs_refresh; then
        _old_version="$(installed_daemon_version 2>/dev/null)"
        [ -n "$_old_version" ] || _old_version="missing or unversioned"
        log_line "Refreshing daemon ($_old_version -> $SCRIPT_VERSION)."
        create_daemon_file
    fi

    if ! daemon_installed; then
        print_line "ERROR: Daemon could not be created."
        print_line ""
        print_line "Expected:"
        print_line "$DAEMON"
        log_line "Start failed. Daemon could not be created."
        return 1
    fi

    chmod +x "$DAEMON" 2>/dev/null

    if [ ! -e /dev/uinput ] && command -v modprobe >/dev/null 2>&1; then
        modprobe uinput >/dev/null 2>&1
    fi

    "$DAEMON" --host "$HOST" --port "$PORT" --path "$WS_PATH" >> "$LOG" 2>&1 &
    _pid="$!"
    echo "$_pid" > "$PID"

    sleep 1

    if daemon_running; then
        print_line "OK: Daemon started."
        log_line "Daemon started with PID $_pid."
        return 0
    fi

    rm -f "$PID" 2>/dev/null
    print_line "ERROR: Daemon failed to start."
    print_line ""
    print_line "Check log:"
    print_line "$LOG"
    log_line "Daemon failed to start."
    return 1
}

restart_daemon() {
    stop_daemon >/dev/null 2>&1
    start_daemon
}

start_stop_daemon() {
    if daemon_running; then
        stop_daemon
    else
        start_daemon
    fi
}

enable_startup() {
    ensure_base
    write_default_config
    mkdir -p "$STARTUP_DIR" 2>/dev/null

    if [ ! -f "$STARTUP" ]; then
        cat > "$STARTUP" <<'EOF'
#!/bin/sh
EOF
        chmod +x "$STARTUP" 2>/dev/null
    fi

    remove_startup_block >/dev/null 2>&1

    cat >> "$STARTUP" <<EOF

# MiSTer Companion Remote BEGIN
# Start MiSTer Companion Remote
$SCRIPT_PATH start --unattended &
# MiSTer Companion Remote END
EOF

    chmod +x "$STARTUP" 2>/dev/null
    print_line "OK: Start on boot enabled."
    log_line "Start on boot enabled."
    return 0
}

disable_startup() {
    if [ ! -f "$STARTUP" ]; then
        print_line "OK: Start on boot already disabled."
        log_line "Start on boot already disabled. user-startup.sh missing."
        return 0
    fi

    if ! remove_startup_block; then
        print_line "ERROR: Could not update:"
        print_line "$STARTUP"
        log_line "Failed to disable start on boot."
        return 1
    fi

    print_line "OK: Start on boot disabled."
    log_line "Start on boot disabled."
    return 0
}

toggle_startup_unattended() {
    if startup_enabled; then
        disable_startup
    else
        enable_startup
    fi
}

uninstall_manager() {
    log_line "Uninstall requested."

    stop_daemon >/dev/null 2>&1
    disable_startup >/dev/null 2>&1

    if [ -d "$BASE" ]; then
        rm -rf "$BASE" 2>/dev/null
    fi

    if [ -f "$SCRIPT_PATH" ]; then
        rm -f "$SCRIPT_PATH" 2>/dev/null
    fi

    print_line "OK: Companion Remote daemon files removed."
    log_line "Daemon files removed."
    return 0
}

show_log() {
    if [ ! -f "$LOG" ]; then
        print_line "No log file found yet."
        return 0
    fi

    print_line "Last log lines:"
    print_line "---------------"

    if command -v tail >/dev/null 2>&1; then
        tail -n 40 "$LOG"
    else
        cat "$LOG"
    fi
}

clear_log() {
    ensure_base
    : > "$LOG"
    print_line "OK: Log cleared."
}

run_menu_action() {
    ACTION="$1"
    RESULT_FILE="$BASE/.last_action_result"

    mkdir -p "$BASE"
    rm -f "$RESULT_FILE"

    case "$ACTION" in
        install)
            install_manager > "$RESULT_FILE" 2>&1
            ACTION_RESULT=$?
            ;;
        start-stop)
            start_stop_daemon > "$RESULT_FILE" 2>&1
            ACTION_RESULT=$?
            ;;
        toggle-boot)
            toggle_startup_unattended > "$RESULT_FILE" 2>&1
            ACTION_RESULT=$?
            ;;
        uninstall)
            uninstall_manager > "$RESULT_FILE" 2>&1
            ACTION_RESULT=$?
            ;;
        *)
            echo "Unknown action: $ACTION" > "$RESULT_FILE"
            ACTION_RESULT=1
            ;;
    esac

    if [ ! -s "$RESULT_FILE" ]; then
        echo "Done." > "$RESULT_FILE"
    fi

    RESULT_TEXT="$(cat "$RESULT_FILE" 2>/dev/null)"
    show_message "$RESULT_TEXT"

    rm -f "$RESULT_FILE" 2>/dev/null
    return $ACTION_RESULT
}

main_menu() {
    if ! has_cmd dialog; then
        echo "dialog was not found. This script requires dialog for controller-friendly menu support."
        exit 1
    fi

    while true; do
        MENU_TEXT="$(status_text)

Choose an option:"

        CHOICE="$(dialog --clear --title "$TITLE" \
            --menu "$MENU_TEXT" 18 82 5 \
            1 "Install / Prepare" \
            2 "Start / Stop Daemon" \
            3 "Toggle Start on Boot" \
            0 "Exit" \
            3>&1 1>&2 2>&3)"

        DIALOG_RESULT=$?
        clear
        sleep 0.3

        if [ $DIALOG_RESULT -ne 0 ]; then
            break
        fi

        case "$CHOICE" in
            1)
                run_menu_action install
                ;;
            2)
                run_menu_action start-stop
                ;;
            3)
                run_menu_action toggle-boot
                ;;
            0)
                break
                ;;
        esac

        clear
        sleep 0.3
    done

    clear
}

usage() {
    print_line "$TITLE"
    print_line ""
    print_line "Usage:"
    print_line "  $SCRIPT_PATH"
    print_line "  $SCRIPT_PATH status --unattended"
    print_line "  $SCRIPT_PATH status-human"
    print_line "  $SCRIPT_PATH install --unattended"
    print_line "  $SCRIPT_PATH uninstall --unattended"
    print_line "  $SCRIPT_PATH start --unattended"
    print_line "  $SCRIPT_PATH stop --unattended"
    print_line "  $SCRIPT_PATH restart --unattended"
    print_line "  $SCRIPT_PATH enable-boot --unattended"
    print_line "  $SCRIPT_PATH disable-boot --unattended"
    print_line "  $SCRIPT_PATH log --unattended"
    print_line "  $SCRIPT_PATH clear-log --unattended"
    print_line ""
    print_line "Direct MiSTer use:"
    print_line "  Run without arguments to open the minimal controller-friendly menu."
}

for arg in "$@"; do
    case "$arg" in
        --unattended)
            UNATTENDED=1
            ;;
        status|status-human|install|uninstall|start|stop|restart|enable-boot|disable-boot|log|clear-log|help)
            if [ -z "$COMMAND" ]; then
                COMMAND="$arg"
            fi
            ;;
    esac
done

if [ -z "$COMMAND" ]; then
    if [ "$UNATTENDED" -eq 1 ]; then
        COMMAND="status"
    else
        main_menu
        exit 0
    fi
fi

case "$COMMAND" in
    status)
        print_status
        ;;
    status-human)
        print_status_human
        ;;
    install)
        install_manager
        ;;
    uninstall)
        uninstall_manager
        ;;
    start)
        start_daemon
        ;;
    stop)
        stop_daemon
        ;;
    restart)
        restart_daemon
        ;;
    enable-boot)
        enable_startup
        ;;
    disable-boot)
        disable_startup
        ;;
    log)
        show_log
        ;;
    clear-log)
        clear_log
        ;;
    help)
        usage
        ;;
    *)
        usage
        exit 1
        ;;
esac

exit $?