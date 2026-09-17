#!/bin/sh

TITLE="MiSTer Companion Remote by Anime0t4ku"
SCRIPT_VERSION="3.0.0"
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
import socket
import struct
import subprocess
import sys
import time
import threading
import fcntl
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

LOGO_PNG = base64.b64decode("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")
HOME_HTML = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover"><meta name="theme-color" content="#120f1c"><title>MiSTer Companion Remote</title><style>\n:root{--bg:#120f1c;--panel:#1b1628;--panel2:#2b2340;--text:#f2ecff;--muted:#b5a9c9;--accent:#8b5cf6;--accent2:#a78bfa;--ok:#39d98a;--danger:#d95768;--border:#3a2f55;--shadow:0 18px 55px rgba(0,0,0,.42)}\n*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html,body{margin:0;min-height:100%;background:radial-gradient(circle at top,#261c3d 0,#120f1c 48%,#0b0911 100%);color:var(--text);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}body{min-height:100dvh}.shell{width:min(1220px,100%);margin:0 auto;padding:16px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 16px;background:rgba(27,22,40,.94);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow);position:relative;z-index:20}.brand{display:flex;align-items:center;gap:12px;min-width:0}.brand img{width:74px;height:auto}.brand-copy{min-width:0}.brand h1{font-size:1rem;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.brand p{margin:3px 0 0;color:var(--muted);font-size:.78rem}.status{display:flex;align-items:center;gap:8px;font-weight:800;font-size:.84rem;white-space:nowrap}.dot{width:10px;height:10px;border-radius:50%;background:#81768f;box-shadow:0 0 0 4px rgba(129,118,143,.12)}.status.connected .dot{background:var(--ok);box-shadow:0 0 0 4px rgba(57,217,138,.13)}.status.disconnected .dot{background:var(--danger);box-shadow:0 0 0 4px rgba(217,87,104,.14)}.nav{display:flex;gap:8px;margin:12px 0}.nav a{flex:1;text-align:center;text-decoration:none;color:var(--text);background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:10px;font-weight:800}.nav a.active,.nav a:hover{background:var(--accent);border-color:var(--accent2)}.card{background:rgba(27,22,40,.96);border:1px solid var(--border);border-radius:22px;box-shadow:var(--shadow)}button{font:inherit;color:inherit}.btn{border:1px solid #5b4a7a;background:linear-gradient(180deg,#352a4f,#241d35);border-radius:14px;min-height:50px;font-weight:900;box-shadow:inset 0 1px rgba(255,255,255,.06),0 5px 14px rgba(0,0,0,.25);cursor:pointer;user-select:none;touch-action:none;transition:transform .06s,background .1s,border-color .1s}.btn.active,.btn:active{transform:translateY(2px) scale(.98);background:var(--accent);border-color:var(--accent2)}.danger{background:#48232d;border-color:#7a3848}.footer{text-align:center;color:var(--muted);font-size:.75rem;padding:14px}.rotate-tip{display:none;position:fixed;inset:0;background:rgba(11,9,17,.94);z-index:100;align-items:center;justify-content:center;padding:24px}.rotate-card{max-width:390px;text-align:center;background:var(--panel);border:1px solid var(--accent);border-radius:22px;padding:26px;box-shadow:var(--shadow)}.rotate-icon{font-size:3rem;margin-bottom:8px}.rotate-card h2{margin:6px 0}.rotate-card p{color:var(--muted);line-height:1.45}.rotate-card .btn{width:100%;margin-top:12px}.toast{position:fixed;left:50%;bottom:20px;transform:translate(-50%,20px);opacity:0;pointer-events:none;background:#2b2340;border:1px solid #5b4a7a;border-radius:12px;padding:11px 16px;z-index:120;transition:.2s;box-shadow:var(--shadow)}.toast.show{opacity:1;transform:translate(-50%,0)}\n@media(max-width:700px){.shell{padding:7px}.topbar{padding:8px 10px;border-radius:14px}.brand img{width:46px}.brand p{display:none}.brand h1{font-size:.82rem}.status{font-size:.7rem}.nav{margin:7px 0;gap:5px}.nav a{padding:7px 4px;font-size:.74rem;border-radius:9px}.footer{display:none}}\n@media(max-width:700px) and (orientation:portrait){.rotate-tip.show{display:flex}}\n\n.home{padding:32px}.hero{text-align:center;max-width:720px;margin:auto}.hero img{width:min(220px,55vw)}.hero h2{font-size:clamp(1.6rem,5vw,2.7rem);margin:8px 0}.hero p{color:var(--muted);line-height:1.55}.choices{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-top:25px}.choice{display:block;text-decoration:none;color:var(--text);padding:24px;border-radius:18px;background:var(--panel2);border:1px solid var(--border);transition:.15s}.choice:hover{transform:translateY(-2px);border-color:var(--accent2)}.choice strong{display:block;font-size:1.18rem;margin-bottom:7px}.choice span{color:var(--muted)}.power{margin-top:20px;padding-top:20px;border-top:1px solid var(--border)}.power h3{margin:0 0 6px}.power p{color:var(--muted);margin:0 0 14px}.power-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.power .soft{background:linear-gradient(180deg,#47366b,#302348);border-color:var(--accent)}.modal{display:none;position:fixed;inset:0;background:rgba(11,9,17,.78);z-index:110;align-items:center;justify-content:center;padding:20px}.modal.show{display:flex}.modal-card{width:min(420px,100%);background:var(--panel);border:1px solid var(--accent);border-radius:20px;padding:22px;box-shadow:var(--shadow)}.modal-card h3{margin-top:0}.modal-card p{color:var(--muted);line-height:1.45}.modal-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:18px}@media(max-width:650px){.home{padding:18px 13px}.choices,.power-grid{grid-template-columns:1fr}.choice{padding:18px}}\n</style></head><body><div class="shell"><header class="topbar"><div class="brand"><img src="/assets/logo.png" alt="MiSTer Companion"><div class="brand-copy"><h1>MiSTer Companion Remote</h1><p>Browser remote v3.0.0</p></div></div><div class="status disconnected"><i class="dot"></i><span>Disconnected</span></div></header><nav class="nav"><a href="/" class="active">Home</a><a href="/controller" class="">Controller</a><a href="/keyboard" class="">Keyboard</a><a href="/games" class="">Games</a><a href="/scripts" class="">Scripts</a></nav><main class="card home"><div class="hero"><img src="/assets/logo.png" alt="MiSTer Companion logo"><p>Choose the dedicated controller or keyboard interface. Everything runs locally on your MiSTer.</p></div><div class="choices"><a class="choice" href="/controller"><strong>Virtual Controller</strong><span>Responsive gamepad controls optimized for landscape use.</span></a><a class="choice" href="/keyboard"><strong>Virtual Keyboard</strong><span>A full keyboard that scales to the available screen.</span></a><a class="choice" href="/games"><strong>Game Launcher</strong><span>Browse installed systems and launch games directly from this MiSTer.</span></a><a class="choice" href="/scripts"><strong>Scripts</strong><span>Browse and launch MiSTer scripts with an interactive console.</span></a><div class="choice" style="cursor:default"><strong>Screenshot</strong><span>Ask MiSTer to capture and save the current screen.</span><button class="btn" style="width:100%;margin-top:14px" onclick="captureScreenshot()">Capture screenshot</button></div></div><section class="screenshot-panel" style="display:none;margin-top:20px;padding-top:20px;border-top:1px solid var(--border)"><img class="screenshot-image" alt="MiSTer screenshot" style="display:block;max-width:100%;max-height:60vh;margin:auto;border-radius:14px;border:1px solid var(--border)"></section><section class="power"><h3>Power actions</h3><div class="power-grid"><button class="btn soft" onclick="askPower(\'soft_reboot\',\'Reload Menu\',\'Reload menu.rbf and return to the MiSTer menu?\')">Reload Menu</button><button class="btn danger" onclick="askPower(\'cold_reboot\',\'Reboot\',\'Fully restart the MiSTer? The web remote will disconnect temporarily.\')">Reboot</button></div></section></main><div class="footer">MiSTer Companion Remote by Anime0t4ku</div></div><div class="modal"><div class="modal-card"><h3 class="modal-title"></h3><p class="modal-text"></p><div class="modal-actions"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn danger confirm-power">Confirm</button></div></div></div><div class="toast"></div><script>\nconst state={ws:null,connected:false,held:new Set(),reconnect:null,heartbeat:null,connecting:false};\nfunction wsURL(){const p=location.protocol===\'https:\'?\'wss\':\'ws\';return `${p}://${location.host}/remote/v1`}\nfunction setStatus(ok){state.connected=ok;document.querySelectorAll(\'.status\').forEach(el=>{el.classList.toggle(\'connected\',ok);el.classList.toggle(\'disconnected\',!ok);el.querySelector(\'span\').textContent=ok?\'Connected\':\'Disconnected\'})}\nfunction connect(){clearTimeout(state.reconnect);if(state.connecting||state.ws?.readyState===WebSocket.OPEN||state.ws?.readyState===WebSocket.CONNECTING)return;state.connecting=true;try{state.ws=new WebSocket(wsURL())}catch(e){state.connecting=false;scheduleReconnect();return}state.ws.onopen=()=>{state.connecting=false;setStatus(true);clearInterval(state.heartbeat);state.heartbeat=setInterval(()=>{if(state.ws?.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:"ping"}))},25000)};state.ws.onclose=()=>{state.connecting=false;clearInterval(state.heartbeat);state.heartbeat=null;setStatus(false);releaseVisuals();scheduleReconnect()};state.ws.onerror=()=>setStatus(false)}\nfunction scheduleReconnect(){clearTimeout(state.reconnect);state.reconnect=setTimeout(connect,1500)}\nfunction send(obj){if(state.ws&&state.ws.readyState===WebSocket.OPEN){state.ws.send(JSON.stringify(obj));return true}showToast(\'Remote is disconnected\');return false}\nfunction ctl(name,action){return send({type:\'controller\',control:[\'up\',\'down\',\'left\',\'right\'].includes(name)?\'dpad\':\'button\',name,action})}\nfunction key(name,action){return send({type:\'keyboard\',key:name,action})}\nfunction systemCommand(command){return send({type:\'system\',command})}\nfunction releaseAll(){if(state.ws&&state.ws.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:\'system\',command:\'release_all\'}));releaseVisuals()}\nfunction releaseVisuals(){state.held.clear();document.querySelectorAll(\'.active\').forEach(el=>el.classList.remove(\'active\'))}\nfunction bindHold(selector,callback){document.querySelectorAll(selector).forEach(el=>{const id=el.dataset.name||el.dataset.key;const down=e=>{e.preventDefault();try{el.setPointerCapture(e.pointerId)}catch(_){}if(state.held.has(el))return;state.held.add(el);el.classList.add(\'active\');callback(id,\'down\')};const up=e=>{e.preventDefault();if(!state.held.has(el))return;state.held.delete(el);el.classList.remove(\'active\');callback(id,\'up\')};el.addEventListener(\'pointerdown\',down);[\'pointerup\',\'pointercancel\',\'lostpointercapture\'].forEach(ev=>el.addEventListener(ev,up));el.addEventListener(\'contextmenu\',e=>e.preventDefault())})}\nfunction showToast(message){const t=document.querySelector(\'.toast\');if(!t)return;t.textContent=message;t.classList.add(\'show\');clearTimeout(t._timer);t._timer=setTimeout(()=>t.classList.remove(\'show\'),2400)}\nfunction setupRotateTip(){const tip=document.querySelector(\'.rotate-tip\');if(!tip)return;const update=()=>{const portrait=matchMedia(\'(orientation: portrait)\').matches&&innerWidth<=700;tip.classList.toggle(\'show\',portrait&&!sessionStorage.getItem(\'remotePortraitDismissed\'))};document.querySelector(\'.rotate-dismiss\')?.addEventListener(\'click\',()=>{sessionStorage.setItem(\'remotePortraitDismissed\',\'1\');tip.classList.remove(\'show\')});addEventListener(\'resize\',update);screen.orientation?.addEventListener?.(\'change\',update);update()}\nwindow.addEventListener(\'blur\',releaseAll);document.addEventListener(\'visibilitychange\',()=>{if(document.hidden)releaseAll()});window.addEventListener(\'beforeunload\',releaseAll);document.addEventListener(\'DOMContentLoaded\',()=>{connect();setupRotateTip()});\n\nfunction captureScreenshot(){const panel=document.querySelector(\'.screenshot-panel\'),img=document.querySelector(\'.screenshot-image\');showToast(\'Capturing screenshot…\');fetch(\'/api/screenshot?fresh=1&_t=\'+Date.now()).then(async r=>{if(!r.ok)throw new Error(await r.text()||\'Screenshot failed\');return r.blob()}).then(blob=>{if(img._url)URL.revokeObjectURL(img._url);img._url=URL.createObjectURL(blob);img.src=img._url;panel.style.display=\'block\';showToast(\'Screenshot captured\')}).catch(e=>showToast(e.message||\'Screenshot failed\'))}\nlet pendingPower=\'\';function askPower(command,title,message){pendingPower=command;document.querySelector(\'.modal-title\').textContent=title;document.querySelector(\'.modal-text\').textContent=message;document.querySelector(\'.modal\').classList.add(\'show\')}function closeModal(){document.querySelector(\'.modal\').classList.remove(\'show\');pendingPower=\'\'}document.querySelector(\'.confirm-power\').addEventListener(\'click\',()=>{const cmd=pendingPower;closeModal();if(systemCommand(cmd))showToast(cmd===\'soft_reboot\'?\'Reloading menu…\':\'Reboot requested…\')});document.querySelector(\'.modal\').addEventListener(\'click\',e=>{if(e.target.classList.contains(\'modal\'))closeModal()});\n</script></body></html>'.encode("utf-8")
CONTROLLER_HTML = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover"><meta name="theme-color" content="#120f1c"><title>Controller · MiSTer Companion Remote</title><style>\n:root{--bg:#120f1c;--panel:#1b1628;--panel2:#2b2340;--text:#f2ecff;--muted:#b5a9c9;--accent:#8b5cf6;--accent2:#a78bfa;--ok:#39d98a;--danger:#d95768;--border:#3a2f55;--shadow:0 18px 55px rgba(0,0,0,.42)}\n*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html,body{margin:0;min-height:100%;background:radial-gradient(circle at top,#261c3d 0,#120f1c 48%,#0b0911 100%);color:var(--text);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}body{min-height:100dvh}.shell{width:min(1220px,100%);margin:0 auto;padding:16px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 16px;background:rgba(27,22,40,.94);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow);position:relative;z-index:20}.brand{display:flex;align-items:center;gap:12px;min-width:0}.brand img{width:74px;height:auto}.brand-copy{min-width:0}.brand h1{font-size:1rem;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.brand p{margin:3px 0 0;color:var(--muted);font-size:.78rem}.status{display:flex;align-items:center;gap:8px;font-weight:800;font-size:.84rem;white-space:nowrap}.dot{width:10px;height:10px;border-radius:50%;background:#81768f;box-shadow:0 0 0 4px rgba(129,118,143,.12)}.status.connected .dot{background:var(--ok);box-shadow:0 0 0 4px rgba(57,217,138,.13)}.status.disconnected .dot{background:var(--danger);box-shadow:0 0 0 4px rgba(217,87,104,.14)}.nav{display:flex;gap:8px;margin:12px 0}.nav a{flex:1;text-align:center;text-decoration:none;color:var(--text);background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:10px;font-weight:800}.nav a.active,.nav a:hover{background:var(--accent);border-color:var(--accent2)}.card{background:rgba(27,22,40,.96);border:1px solid var(--border);border-radius:22px;box-shadow:var(--shadow)}button{font:inherit;color:inherit}.btn{border:1px solid #5b4a7a;background:linear-gradient(180deg,#352a4f,#241d35);border-radius:14px;min-height:50px;font-weight:900;box-shadow:inset 0 1px rgba(255,255,255,.06),0 5px 14px rgba(0,0,0,.25);cursor:pointer;user-select:none;touch-action:none;transition:transform .06s,background .1s,border-color .1s}.btn.active,.btn:active{transform:translateY(2px) scale(.98);background:var(--accent);border-color:var(--accent2)}.danger{background:#48232d;border-color:#7a3848}.footer{text-align:center;color:var(--muted);font-size:.75rem;padding:14px}.rotate-tip{display:none;position:fixed;inset:0;background:rgba(11,9,17,.94);z-index:100;align-items:center;justify-content:center;padding:24px}.rotate-card{max-width:390px;text-align:center;background:var(--panel);border:1px solid var(--accent);border-radius:22px;padding:26px;box-shadow:var(--shadow)}.rotate-icon{font-size:3rem;margin-bottom:8px}.rotate-card h2{margin:6px 0}.rotate-card p{color:var(--muted);line-height:1.45}.rotate-card .btn{width:100%;margin-top:12px}.toast{position:fixed;left:50%;bottom:20px;transform:translate(-50%,20px);opacity:0;pointer-events:none;background:#2b2340;border:1px solid #5b4a7a;border-radius:12px;padding:11px 16px;z-index:120;transition:.2s;box-shadow:var(--shadow)}.toast.show{opacity:1;transform:translate(-50%,0)}\n@media(max-width:700px){.shell{padding:7px}.topbar{padding:8px 10px;border-radius:14px}.brand img{width:46px}.brand p{display:none}.brand h1{font-size:.82rem}.status{font-size:.7rem}.nav{margin:7px 0;gap:5px}.nav a{padding:7px 4px;font-size:.74rem;border-radius:9px}.footer{display:none}}\n@media(max-width:700px) and (orientation:portrait){.rotate-tip.show{display:flex}}\n\n.stage{position:relative;width:100%;overflow:hidden}.scale-box{position:absolute;left:50%;top:0;width:1000px;height:560px;transform-origin:top center;transform:translateX(-50%) scale(var(--ui-scale,1))}.controller-card{width:1000px;height:560px;padding:18px}.shoulders{display:grid;grid-template-columns:1fr 1fr;gap:20px}.shoulders .btn{height:58px}.controller-wrap{display:grid;grid-template-columns:330px 1fr 330px;gap:24px;align-items:center;height:390px}.section-label{text-align:center;color:var(--muted);font-weight:800;font-size:.75rem;letter-spacing:.08em;text-transform:uppercase;margin-bottom:10px}.dpad{display:grid;grid-template-columns:repeat(3,88px);grid-template-rows:repeat(3,88px);justify-content:center}.dpad .btn{border-radius:18px;font-size:1.55rem}.up{grid-column:2}.left{grid-column:1;grid-row:2}.right{grid-column:3;grid-row:2}.down{grid-column:2;grid-row:3}.dpad-center{grid-column:2;grid-row:2;background:#100c18;border:1px solid #302442;border-radius:18px}.center-buttons{display:grid;gap:10px}.center-buttons .btn{height:54px}.face{position:relative;width:280px;height:280px;margin:auto}.face .btn{position:absolute;width:88px;height:88px;border-radius:50%;font-size:1.25rem}.face .x{top:0;left:96px}.face .y{top:96px;left:0}.face .a{top:96px;right:0}.face .b{bottom:0;left:96px}.release{width:100%;height:48px}@media(max-width:700px){.stage{margin-top:0}.scale-box{top:0}}\n</style></head><body><div class="shell"><header class="topbar"><div class="brand"><img src="/assets/logo.png" alt="MiSTer Companion"><div class="brand-copy"><h1>MiSTer Companion Remote</h1><p>Browser remote v3.0.0</p></div></div><div class="status disconnected"><i class="dot"></i><span>Disconnected</span></div></header><nav class="nav"><a href="/" class="">Home</a><a href="/controller" class="active">Controller</a><a href="/keyboard" class="">Keyboard</a><a href="/games" class="">Games</a><a href="/scripts" class="">Scripts</a></nav><div class="stage"><div class="scale-box"><main class="card controller-card"><div class="shoulders"><button class="btn control" data-name="l">L</button><button class="btn control" data-name="r">R</button></div><div class="controller-wrap"><section><div class="section-label">D-Pad</div><div class="dpad"><button class="btn control up" data-name="up">▲</button><button class="btn control left" data-name="left">◀</button><div class="dpad-center"></div><button class="btn control right" data-name="right">▶</button><button class="btn control down" data-name="down">▼</button></div></section><section><div class="section-label">System</div><div class="center-buttons"><button class="btn control" data-name="select">Select</button><button class="btn control" data-name="home">Home</button><button class="btn control" data-name="start">Start</button></div></section><section><div class="section-label">Buttons</div><div class="face"><button class="btn control x" data-name="x">X</button><button class="btn control y" data-name="y">Y</button><button class="btn control a" data-name="a">A</button><button class="btn control b" data-name="b">B</button></div></section></div><button class="btn danger release" onclick="releaseAll()">Release all inputs</button></main></div></div><div class="footer">MiSTer Companion Remote by Anime0t4ku</div></div><div class="rotate-tip"><div class="rotate-card"><div class="rotate-icon">↻</div><h2>Rotate your phone</h2><p>The remote is designed to use the available screen best in landscape orientation.</p><button class="btn rotate-dismiss">Continue in portrait</button></div></div><div class="toast"></div><script>\nconst state={ws:null,connected:false,held:new Set(),reconnect:null,heartbeat:null,connecting:false};\nfunction wsURL(){const p=location.protocol===\'https:\'?\'wss\':\'ws\';return `${p}://${location.host}/remote/v1`}\nfunction setStatus(ok){state.connected=ok;document.querySelectorAll(\'.status\').forEach(el=>{el.classList.toggle(\'connected\',ok);el.classList.toggle(\'disconnected\',!ok);el.querySelector(\'span\').textContent=ok?\'Connected\':\'Disconnected\'})}\nfunction connect(){clearTimeout(state.reconnect);if(state.connecting||state.ws?.readyState===WebSocket.OPEN||state.ws?.readyState===WebSocket.CONNECTING)return;state.connecting=true;try{state.ws=new WebSocket(wsURL())}catch(e){state.connecting=false;scheduleReconnect();return}state.ws.onopen=()=>{state.connecting=false;setStatus(true);clearInterval(state.heartbeat);state.heartbeat=setInterval(()=>{if(state.ws?.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:"ping"}))},25000)};state.ws.onclose=()=>{state.connecting=false;clearInterval(state.heartbeat);state.heartbeat=null;setStatus(false);releaseVisuals();scheduleReconnect()};state.ws.onerror=()=>setStatus(false)}\nfunction scheduleReconnect(){clearTimeout(state.reconnect);state.reconnect=setTimeout(connect,1500)}\nfunction send(obj){if(state.ws&&state.ws.readyState===WebSocket.OPEN){state.ws.send(JSON.stringify(obj));return true}showToast(\'Remote is disconnected\');return false}\nfunction ctl(name,action){return send({type:\'controller\',control:[\'up\',\'down\',\'left\',\'right\'].includes(name)?\'dpad\':\'button\',name,action})}\nfunction key(name,action){return send({type:\'keyboard\',key:name,action})}\nfunction systemCommand(command){return send({type:\'system\',command})}\nfunction releaseAll(){if(state.ws&&state.ws.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:\'system\',command:\'release_all\'}));releaseVisuals()}\nfunction releaseVisuals(){state.held.clear();document.querySelectorAll(\'.active\').forEach(el=>el.classList.remove(\'active\'))}\nfunction bindHold(selector,callback){document.querySelectorAll(selector).forEach(el=>{const id=el.dataset.name||el.dataset.key;const down=e=>{e.preventDefault();try{el.setPointerCapture(e.pointerId)}catch(_){}if(state.held.has(el))return;state.held.add(el);el.classList.add(\'active\');callback(id,\'down\')};const up=e=>{e.preventDefault();if(!state.held.has(el))return;state.held.delete(el);el.classList.remove(\'active\');callback(id,\'up\')};el.addEventListener(\'pointerdown\',down);[\'pointerup\',\'pointercancel\',\'lostpointercapture\'].forEach(ev=>el.addEventListener(ev,up));el.addEventListener(\'contextmenu\',e=>e.preventDefault())})}\nfunction showToast(message){const t=document.querySelector(\'.toast\');if(!t)return;t.textContent=message;t.classList.add(\'show\');clearTimeout(t._timer);t._timer=setTimeout(()=>t.classList.remove(\'show\'),2400)}\nfunction setupRotateTip(){const tip=document.querySelector(\'.rotate-tip\');if(!tip)return;const update=()=>{const portrait=matchMedia(\'(orientation: portrait)\').matches&&innerWidth<=700;tip.classList.toggle(\'show\',portrait&&!sessionStorage.getItem(\'remotePortraitDismissed\'))};document.querySelector(\'.rotate-dismiss\')?.addEventListener(\'click\',()=>{sessionStorage.setItem(\'remotePortraitDismissed\',\'1\');tip.classList.remove(\'show\')});addEventListener(\'resize\',update);screen.orientation?.addEventListener?.(\'change\',update);update()}\nwindow.addEventListener(\'blur\',releaseAll);document.addEventListener(\'visibilitychange\',()=>{if(document.hidden)releaseAll()});window.addEventListener(\'beforeunload\',releaseAll);document.addEventListener(\'DOMContentLoaded\',()=>{connect();setupRotateTip()});\n\nfunction fitUI(){const stage=document.querySelector(\'.stage\');if(!stage)return;const vv=window.visualViewport;const vh=vv?vv.height:innerHeight;const top=stage.getBoundingClientRect().top-(vv?vv.offsetTop:0);const aw=Math.max(240,stage.clientWidth);const ah=Math.max(180,vh-top-6);const scale=Math.min(aw/1000,ah/560,1.18);document.documentElement.style.setProperty(\'--ui-scale\',scale);stage.style.height=(560*scale)+\'px\'}document.addEventListener(\'DOMContentLoaded\',()=>{bindHold(\'.control\',ctl);fitUI()});addEventListener(\'resize\',fitUI);visualViewport?.addEventListener(\'resize\',fitUI);screen.orientation?.addEventListener?.(\'change\',()=>setTimeout(fitUI,80));\n</script></body></html>'.encode("utf-8")
KEYBOARD_HTML = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover"><meta name="theme-color" content="#120f1c"><title>Keyboard · MiSTer Companion Remote</title><style>\n:root{--bg:#120f1c;--panel:#1b1628;--panel2:#2b2340;--text:#f2ecff;--muted:#b5a9c9;--accent:#8b5cf6;--accent2:#a78bfa;--ok:#39d98a;--danger:#d95768;--border:#3a2f55;--shadow:0 18px 55px rgba(0,0,0,.42)}\n*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html,body{margin:0;min-height:100%;background:radial-gradient(circle at top,#261c3d 0,#120f1c 48%,#0b0911 100%);color:var(--text);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}body{min-height:100dvh}.shell{width:min(1220px,100%);margin:0 auto;padding:16px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 16px;background:rgba(27,22,40,.94);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow);position:relative;z-index:20}.brand{display:flex;align-items:center;gap:12px;min-width:0}.brand img{width:74px;height:auto}.brand-copy{min-width:0}.brand h1{font-size:1rem;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.brand p{margin:3px 0 0;color:var(--muted);font-size:.78rem}.status{display:flex;align-items:center;gap:8px;font-weight:800;font-size:.84rem;white-space:nowrap}.dot{width:10px;height:10px;border-radius:50%;background:#81768f;box-shadow:0 0 0 4px rgba(129,118,143,.12)}.status.connected .dot{background:var(--ok);box-shadow:0 0 0 4px rgba(57,217,138,.13)}.status.disconnected .dot{background:var(--danger);box-shadow:0 0 0 4px rgba(217,87,104,.14)}.nav{display:flex;gap:8px;margin:12px 0}.nav a{flex:1;text-align:center;text-decoration:none;color:var(--text);background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:10px;font-weight:800}.nav a.active,.nav a:hover{background:var(--accent);border-color:var(--accent2)}.card{background:rgba(27,22,40,.96);border:1px solid var(--border);border-radius:22px;box-shadow:var(--shadow)}button{font:inherit;color:inherit}.btn{border:1px solid #5b4a7a;background:linear-gradient(180deg,#352a4f,#241d35);border-radius:14px;min-height:50px;font-weight:900;box-shadow:inset 0 1px rgba(255,255,255,.06),0 5px 14px rgba(0,0,0,.25);cursor:pointer;user-select:none;touch-action:none;transition:transform .06s,background .1s,border-color .1s}.btn.active,.btn:active{transform:translateY(2px) scale(.98);background:var(--accent);border-color:var(--accent2)}.danger{background:#48232d;border-color:#7a3848}.footer{text-align:center;color:var(--muted);font-size:.75rem;padding:14px}.rotate-tip{display:none;position:fixed;inset:0;background:rgba(11,9,17,.94);z-index:100;align-items:center;justify-content:center;padding:24px}.rotate-card{max-width:390px;text-align:center;background:var(--panel);border:1px solid var(--accent);border-radius:22px;padding:26px;box-shadow:var(--shadow)}.rotate-icon{font-size:3rem;margin-bottom:8px}.rotate-card h2{margin:6px 0}.rotate-card p{color:var(--muted);line-height:1.45}.rotate-card .btn{width:100%;margin-top:12px}.toast{position:fixed;left:50%;bottom:20px;transform:translate(-50%,20px);opacity:0;pointer-events:none;background:#2b2340;border:1px solid #5b4a7a;border-radius:12px;padding:11px 16px;z-index:120;transition:.2s;box-shadow:var(--shadow)}.toast.show{opacity:1;transform:translate(-50%,0)}\n@media(max-width:700px){.shell{padding:7px}.topbar{padding:8px 10px;border-radius:14px}.brand img{width:46px}.brand p{display:none}.brand h1{font-size:.82rem}.status{font-size:.7rem}.nav{margin:7px 0;gap:5px}.nav a{padding:7px 4px;font-size:.74rem;border-radius:9px}.footer{display:none}}\n@media(max-width:700px) and (orientation:portrait){.rotate-tip.show{display:flex}}\n\n.stage{position:relative;width:100%;overflow:hidden}.scale-box{position:absolute;left:50%;top:0;width:1180px;height:520px;transform-origin:top center;transform:translateX(-50%) scale(var(--ui-scale,1))}.keyboard-card{width:1180px;height:520px;padding:14px}.keyboard-tools{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.keyboard-tools h2{margin:0;font-size:1.05rem}.keyboard-tools .btn{min-height:38px;padding:0 14px}.key-row{display:flex;gap:5px;margin-bottom:5px}.key{flex:var(--w,1);min-width:0;height:53px;border-radius:9px;font-size:.78rem;padding:0 3px}.bottom{display:grid;grid-template-columns:1fr 230px;gap:10px}.nav-cluster{display:grid;grid-template-columns:repeat(6,1fr);gap:5px}.nav-cluster .key{height:44px}.arrows{display:grid;grid-template-columns:repeat(3,1fr);grid-template-rows:repeat(2,44px);gap:5px}.arrows .key{height:44px}.au{grid-column:2}.al{grid-column:1;grid-row:2}.ad{grid-column:2;grid-row:2}.ar{grid-column:3;grid-row:2}\n</style></head><body><div class="shell"><header class="topbar"><div class="brand"><img src="/assets/logo.png" alt="MiSTer Companion"><div class="brand-copy"><h1>MiSTer Companion Remote</h1><p>Browser remote v3.0.0</p></div></div><div class="status disconnected"><i class="dot"></i><span>Disconnected</span></div></header><nav class="nav"><a href="/" class="">Home</a><a href="/controller" class="">Controller</a><a href="/keyboard" class="active">Keyboard</a><a href="/games" class="">Games</a><a href="/scripts" class="">Scripts</a></nav><div class="stage"><div class="scale-box"><main class="card keyboard-card"><div class="keyboard-tools"><h2>Virtual Keyboard</h2><button class="btn danger" onclick="releaseAll()">Release all inputs</button></div><div class="key-row"><button class="btn key" style="--w:1" data-key="KEY_ESC">Esc</button><button class="btn key" style="--w:1" data-key="KEY_F1">F1</button><button class="btn key" style="--w:1" data-key="KEY_F2">F2</button><button class="btn key" style="--w:1" data-key="KEY_F3">F3</button><button class="btn key" style="--w:1" data-key="KEY_F4">F4</button><button class="btn key" style="--w:1" data-key="KEY_F5">F5</button><button class="btn key" style="--w:1" data-key="KEY_F6">F6</button><button class="btn key" style="--w:1" data-key="KEY_F7">F7</button><button class="btn key" style="--w:1" data-key="KEY_F8">F8</button><button class="btn key" style="--w:1" data-key="KEY_F9">F9</button><button class="btn key" style="--w:1" data-key="KEY_F10">F10</button><button class="btn key" style="--w:1" data-key="KEY_F11">F11</button><button class="btn key" style="--w:1" data-key="KEY_F12">F12</button></div><div class="key-row"><button class="btn key" style="--w:1" data-key="KEY_GRAVE">`</button><button class="btn key" style="--w:1" data-key="KEY_1">1</button><button class="btn key" style="--w:1" data-key="KEY_2">2</button><button class="btn key" style="--w:1" data-key="KEY_3">3</button><button class="btn key" style="--w:1" data-key="KEY_4">4</button><button class="btn key" style="--w:1" data-key="KEY_5">5</button><button class="btn key" style="--w:1" data-key="KEY_6">6</button><button class="btn key" style="--w:1" data-key="KEY_7">7</button><button class="btn key" style="--w:1" data-key="KEY_8">8</button><button class="btn key" style="--w:1" data-key="KEY_9">9</button><button class="btn key" style="--w:1" data-key="KEY_0">0</button><button class="btn key" style="--w:1" data-key="KEY_MINUS">-</button><button class="btn key" style="--w:1" data-key="KEY_EQUAL">=</button><button class="btn key" style="--w:2" data-key="KEY_BACKSPACE">Backspace</button></div><div class="key-row"><button class="btn key" style="--w:1.5" data-key="KEY_TAB">Tab</button><button class="btn key" style="--w:1" data-key="KEY_Q">Q</button><button class="btn key" style="--w:1" data-key="KEY_W">W</button><button class="btn key" style="--w:1" data-key="KEY_E">E</button><button class="btn key" style="--w:1" data-key="KEY_R">R</button><button class="btn key" style="--w:1" data-key="KEY_T">T</button><button class="btn key" style="--w:1" data-key="KEY_Y">Y</button><button class="btn key" style="--w:1" data-key="KEY_U">U</button><button class="btn key" style="--w:1" data-key="KEY_I">I</button><button class="btn key" style="--w:1" data-key="KEY_O">O</button><button class="btn key" style="--w:1" data-key="KEY_P">P</button><button class="btn key" style="--w:1" data-key="KEY_LEFTBRACE">[</button><button class="btn key" style="--w:1" data-key="KEY_RIGHTBRACE">]</button><button class="btn key" style="--w:1.5" data-key="KEY_BACKSLASH">\\</button></div><div class="key-row"><button class="btn key" style="--w:1.7" data-key="KEY_CAPSLOCK">Caps</button><button class="btn key" style="--w:1" data-key="KEY_A">A</button><button class="btn key" style="--w:1" data-key="KEY_S">S</button><button class="btn key" style="--w:1" data-key="KEY_D">D</button><button class="btn key" style="--w:1" data-key="KEY_F">F</button><button class="btn key" style="--w:1" data-key="KEY_G">G</button><button class="btn key" style="--w:1" data-key="KEY_H">H</button><button class="btn key" style="--w:1" data-key="KEY_J">J</button><button class="btn key" style="--w:1" data-key="KEY_K">K</button><button class="btn key" style="--w:1" data-key="KEY_L">L</button><button class="btn key" style="--w:1" data-key="KEY_SEMICOLON">;</button><button class="btn key" style="--w:1" data-key="KEY_APOSTROPHE">\'</button><button class="btn key" style="--w:2.3" data-key="KEY_ENTER">Enter</button></div><div class="key-row"><button class="btn key" style="--w:2.2" data-key="KEY_LEFTSHIFT">Shift</button><button class="btn key" style="--w:1" data-key="KEY_Z">Z</button><button class="btn key" style="--w:1" data-key="KEY_X">X</button><button class="btn key" style="--w:1" data-key="KEY_C">C</button><button class="btn key" style="--w:1" data-key="KEY_V">V</button><button class="btn key" style="--w:1" data-key="KEY_B">B</button><button class="btn key" style="--w:1" data-key="KEY_N">N</button><button class="btn key" style="--w:1" data-key="KEY_M">M</button><button class="btn key" style="--w:1" data-key="KEY_COMMA">,</button><button class="btn key" style="--w:1" data-key="KEY_DOT">.</button><button class="btn key" style="--w:1" data-key="KEY_SLASH">/</button><button class="btn key" style="--w:2.6" data-key="KEY_RIGHTSHIFT">Shift</button></div><div class="key-row"><button class="btn key" style="--w:1.5" data-key="KEY_LEFTCTRL">Ctrl</button><button class="btn key" style="--w:1.5" data-key="KEY_LEFTALT">Alt</button><button class="btn key" style="--w:7" data-key="KEY_SPACE">Space</button><button class="btn key" style="--w:1.5" data-key="KEY_RIGHTALT">Alt</button><button class="btn key" style="--w:1.5" data-key="KEY_RIGHTCTRL">Ctrl</button></div><div class="bottom"><div class="nav-cluster"><button class="btn key" data-key="KEY_INSERT">Ins</button><button class="btn key" data-key="KEY_DELETE">Del</button><button class="btn key" data-key="KEY_HOME">Home</button><button class="btn key" data-key="KEY_END">End</button><button class="btn key" data-key="KEY_PAGEUP">PgUp</button><button class="btn key" data-key="KEY_PAGEDOWN">PgDn</button></div><div class="arrows"><button class="btn key au" data-key="KEY_UP">▲</button><button class="btn key al" data-key="KEY_LEFT">◀</button><button class="btn key ad" data-key="KEY_DOWN">▼</button><button class="btn key ar" data-key="KEY_RIGHT">▶</button></div></div></main></div></div><div class="footer">MiSTer Companion Remote by Anime0t4ku</div></div><div class="rotate-tip"><div class="rotate-card"><div class="rotate-icon">↻</div><h2>Rotate your phone</h2><p>The remote is designed to use the available screen best in landscape orientation.</p><button class="btn rotate-dismiss">Continue in portrait</button></div></div><div class="toast"></div><script>\nconst state={ws:null,connected:false,held:new Set(),reconnect:null,heartbeat:null,connecting:false};\nfunction wsURL(){const p=location.protocol===\'https:\'?\'wss\':\'ws\';return `${p}://${location.host}/remote/v1`}\nfunction setStatus(ok){state.connected=ok;document.querySelectorAll(\'.status\').forEach(el=>{el.classList.toggle(\'connected\',ok);el.classList.toggle(\'disconnected\',!ok);el.querySelector(\'span\').textContent=ok?\'Connected\':\'Disconnected\'})}\nfunction connect(){clearTimeout(state.reconnect);if(state.connecting||state.ws?.readyState===WebSocket.OPEN||state.ws?.readyState===WebSocket.CONNECTING)return;state.connecting=true;try{state.ws=new WebSocket(wsURL())}catch(e){state.connecting=false;scheduleReconnect();return}state.ws.onopen=()=>{state.connecting=false;setStatus(true);clearInterval(state.heartbeat);state.heartbeat=setInterval(()=>{if(state.ws?.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:"ping"}))},25000)};state.ws.onclose=()=>{state.connecting=false;clearInterval(state.heartbeat);state.heartbeat=null;setStatus(false);releaseVisuals();scheduleReconnect()};state.ws.onerror=()=>setStatus(false)}\nfunction scheduleReconnect(){clearTimeout(state.reconnect);state.reconnect=setTimeout(connect,1500)}\nfunction send(obj){if(state.ws&&state.ws.readyState===WebSocket.OPEN){state.ws.send(JSON.stringify(obj));return true}showToast(\'Remote is disconnected\');return false}\nfunction ctl(name,action){return send({type:\'controller\',control:[\'up\',\'down\',\'left\',\'right\'].includes(name)?\'dpad\':\'button\',name,action})}\nfunction key(name,action){return send({type:\'keyboard\',key:name,action})}\nfunction systemCommand(command){return send({type:\'system\',command})}\nfunction releaseAll(){if(state.ws&&state.ws.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:\'system\',command:\'release_all\'}));releaseVisuals()}\nfunction releaseVisuals(){state.held.clear();document.querySelectorAll(\'.active\').forEach(el=>el.classList.remove(\'active\'))}\nfunction bindHold(selector,callback){document.querySelectorAll(selector).forEach(el=>{const id=el.dataset.name||el.dataset.key;const down=e=>{e.preventDefault();try{el.setPointerCapture(e.pointerId)}catch(_){}if(state.held.has(el))return;state.held.add(el);el.classList.add(\'active\');callback(id,\'down\')};const up=e=>{e.preventDefault();if(!state.held.has(el))return;state.held.delete(el);el.classList.remove(\'active\');callback(id,\'up\')};el.addEventListener(\'pointerdown\',down);[\'pointerup\',\'pointercancel\',\'lostpointercapture\'].forEach(ev=>el.addEventListener(ev,up));el.addEventListener(\'contextmenu\',e=>e.preventDefault())})}\nfunction showToast(message){const t=document.querySelector(\'.toast\');if(!t)return;t.textContent=message;t.classList.add(\'show\');clearTimeout(t._timer);t._timer=setTimeout(()=>t.classList.remove(\'show\'),2400)}\nfunction setupRotateTip(){const tip=document.querySelector(\'.rotate-tip\');if(!tip)return;const update=()=>{const portrait=matchMedia(\'(orientation: portrait)\').matches&&innerWidth<=700;tip.classList.toggle(\'show\',portrait&&!sessionStorage.getItem(\'remotePortraitDismissed\'))};document.querySelector(\'.rotate-dismiss\')?.addEventListener(\'click\',()=>{sessionStorage.setItem(\'remotePortraitDismissed\',\'1\');tip.classList.remove(\'show\')});addEventListener(\'resize\',update);screen.orientation?.addEventListener?.(\'change\',update);update()}\nwindow.addEventListener(\'blur\',releaseAll);document.addEventListener(\'visibilitychange\',()=>{if(document.hidden)releaseAll()});window.addEventListener(\'beforeunload\',releaseAll);document.addEventListener(\'DOMContentLoaded\',()=>{connect();setupRotateTip()});\n\nconst browserMap={Escape:\'KEY_ESC\',Backspace:\'KEY_BACKSPACE\',Tab:\'KEY_TAB\',Enter:\'KEY_ENTER\',ShiftLeft:\'KEY_LEFTSHIFT\',ShiftRight:\'KEY_RIGHTSHIFT\',ControlLeft:\'KEY_LEFTCTRL\',ControlRight:\'KEY_RIGHTCTRL\',AltLeft:\'KEY_LEFTALT\',AltRight:\'KEY_RIGHTALT\',Space:\'KEY_SPACE\',CapsLock:\'KEY_CAPSLOCK\',ArrowUp:\'KEY_UP\',ArrowDown:\'KEY_DOWN\',ArrowLeft:\'KEY_LEFT\',ArrowRight:\'KEY_RIGHT\',Home:\'KEY_HOME\',End:\'KEY_END\',PageUp:\'KEY_PAGEUP\',PageDown:\'KEY_PAGEDOWN\',Insert:\'KEY_INSERT\',Delete:\'KEY_DELETE\'};for(let i=1;i<=12;i++)browserMap[\'F\'+i]=\'KEY_F\'+i;for(let i=0;i<=9;i++)browserMap[\'Digit\'+i]=\'KEY_\'+i;for(const c of \'ABCDEFGHIJKLMNOPQRSTUVWXYZ\')browserMap[\'Key\'+c]=\'KEY_\'+c;Object.assign(browserMap,{Minus:\'KEY_MINUS\',Equal:\'KEY_EQUAL\',BracketLeft:\'KEY_LEFTBRACE\',BracketRight:\'KEY_RIGHTBRACE\',Backslash:\'KEY_BACKSLASH\',Semicolon:\'KEY_SEMICOLON\',Quote:\'KEY_APOSTROPHE\',Backquote:\'KEY_GRAVE\',Comma:\'KEY_COMMA\',Period:\'KEY_DOT\',Slash:\'KEY_SLASH\'});const physicalHeld=new Set();function fitUI(){const stage=document.querySelector(\'.stage\');if(!stage)return;const vv=window.visualViewport;const vh=vv?vv.height:innerHeight;const top=stage.getBoundingClientRect().top-(vv?vv.offsetTop:0);const aw=Math.max(260,stage.clientWidth);const ah=Math.max(180,vh-top-6);const scale=Math.min(aw/1180,ah/520,1);document.documentElement.style.setProperty(\'--ui-scale\',scale);stage.style.height=(520*scale)+\'px\'}document.addEventListener(\'DOMContentLoaded\',()=>{bindHold(\'.key\',key);fitUI()});addEventListener(\'resize\',fitUI);visualViewport?.addEventListener(\'resize\',fitUI);screen.orientation?.addEventListener?.(\'change\',()=>setTimeout(fitUI,80));window.addEventListener(\'keydown\',e=>{const k=browserMap[e.code];if(!k||physicalHeld.has(k))return;e.preventDefault();physicalHeld.add(k);key(k,\'down\')});window.addEventListener(\'keyup\',e=>{const k=browserMap[e.code];if(!k)return;e.preventDefault();physicalHeld.delete(k);key(k,\'up\')});window.addEventListener(\'blur\',()=>physicalHeld.clear());\n</script></body></html>'.encode("utf-8")



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
:root{--bg:#120f1c;--panel:#1b1628;--panel2:#2b2340;--text:#f2ecff;--muted:#b5a9c9;--accent:#8b5cf6;--accent2:#a78bfa;--ok:#39d98a;--danger:#d95768;--border:#3a2f55;--shadow:0 18px 55px rgba(0,0,0,.42)}*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:radial-gradient(circle at top,#261c3d 0,#120f1c 48%,#0b0911 100%);color:var(--text);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.shell{width:min(1220px,100%);margin:auto;padding:16px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 16px;background:rgba(27,22,40,.94);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow)}.brand{display:flex;align-items:center;gap:12px}.brand img{width:74px}.brand h1{font-size:1rem;margin:0}.brand p{margin:3px 0 0;color:var(--muted);font-size:.78rem}.nav{display:flex;gap:8px;margin:12px 0}.nav a{flex:1;text-align:center;text-decoration:none;color:var(--text);background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:10px;font-weight:800}.nav a.active,.nav a:hover{background:var(--accent);border-color:var(--accent2)}.card{background:rgba(27,22,40,.96);border:1px solid var(--border);border-radius:22px;box-shadow:var(--shadow)}.tools{display:grid;grid-template-columns:minmax(180px,280px) minmax(150px,190px) 1fr;gap:10px;padding:14px;border-bottom:1px solid var(--border)}.tools select,.tools input{width:100%;min-height:46px;border-radius:12px;border:1px solid var(--border);background:var(--panel2);color:var(--text);padding:0 12px;font:inherit}.summary{color:var(--muted);font-size:.76rem;padding:10px 14px 0}.games{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px;padding:14px}.game{overflow:hidden;background:var(--panel2);border:1px solid var(--border);border-radius:16px;cursor:pointer;transition:.12s}.game:hover{transform:translateY(-2px);border-color:var(--accent2)}.art{height:180px;background:#100c18;display:flex;align-items:center;justify-content:center;color:var(--muted);overflow:hidden}.art img{width:100%;height:100%;object-fit:contain}.game h3{font-size:.9rem;margin:10px 11px 4px;line-height:1.25}.game p{color:var(--muted);font-size:.72rem;margin:0 11px 12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.system-tag{display:inline-block;color:var(--accent2);font-size:.68rem;font-weight:800;margin:8px 11px 0}.games.list-view{display:block}.games.list-view .game{display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-areas:'title system' 'path system';align-items:center;gap:2px 12px;padding:10px 12px;margin-bottom:7px;border-radius:12px}.games.list-view .game h3{grid-area:title;margin:0;font-size:.9rem}.games.list-view .game p{grid-area:path;margin:2px 0 0;font-size:.72rem}.games.list-view .system-tag{grid-area:system;margin:0;white-space:nowrap}.empty{padding:40px;text-align:center;color:var(--muted)}.load-more-wrap{text-align:center;padding:0 14px 18px}.load-more{border:1px solid #5b4a7a;background:linear-gradient(180deg,#352a4f,#241d35);color:var(--text);border-radius:12px;min-height:44px;padding:0 24px;font-weight:800;cursor:pointer}.load-more[hidden]{display:none}.toast{position:fixed;left:50%;bottom:20px;transform:translate(-50%,20px);opacity:0;background:#2b2340;border:1px solid #5b4a7a;border-radius:12px;padding:11px 16px;z-index:120;transition:.2s}.toast.show{opacity:1;transform:translate(-50%,0)}@media(max-width:700px){.shell{padding:7px}.brand img{width:46px}.brand p{display:none}.nav{gap:5px}.nav a{padding:7px 3px;font-size:.72rem}.tools{grid-template-columns:1fr;padding:8px}.games{grid-template-columns:repeat(2,minmax(0,1fr));padding:8px;gap:8px}.art{height:145px}}
</style></head><body><div class="shell"><header class="topbar"><div class="brand"><img src="/assets/logo.png" alt="MiSTer Companion"><div><h1>MiSTer Companion Remote</h1><p>Browser remote v3.0.0</p></div></div></header><nav class="nav"><a href="/">Home</a><a href="/controller">Controller</a><a href="/keyboard">Keyboard</a><a href="/games" class="active">Games</a><a href="/scripts">Scripts</a></nav><main class="card"><div class="tools"><select id="system"><option>Loading systems…</option></select><select id="view" aria-label="Game view"><option value="artwork">Artwork view</option><option value="list">List view</option></select><input id="search" type="search" placeholder="Search games"></div><div class="summary" id="summary"></div><div class="games" id="games"><div class="empty">Loading systems…</div></div><div class="load-more-wrap"><button class="load-more" id="more" hidden>Load more</button></div></main></div><div class="toast"></div><script>
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
:root{--bg:#120f1c;--panel:#1b1628;--panel2:#2b2340;--text:#f2ecff;--muted:#b5a9c9;--accent:#8b5cf6;--accent2:#a78bfa;--danger:#d95768;--border:#3a2f55;--shadow:0 18px 55px rgba(0,0,0,.42)}*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:radial-gradient(circle at top,#261c3d 0,#120f1c 48%,#0b0911 100%);color:var(--text);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.shell{width:min(1220px,100%);margin:auto;padding:16px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 16px;background:rgba(27,22,40,.94);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow)}.brand{display:flex;align-items:center;gap:12px}.brand img{width:74px}.brand h1{font-size:1rem;margin:0}.brand p{margin:3px 0 0;color:var(--muted);font-size:.78rem}.nav{display:flex;gap:8px;margin:12px 0}.nav a{flex:1;text-align:center;text-decoration:none;color:var(--text);background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:10px;font-weight:800}.nav a.active,.nav a:hover{background:var(--accent);border-color:var(--accent2)}.card{background:rgba(27,22,40,.96);border:1px solid var(--border);border-radius:22px;box-shadow:var(--shadow)}.tools{display:grid;grid-template-columns:1fr auto auto;gap:10px;padding:14px;border-bottom:1px solid var(--border)}input{min-height:46px;border-radius:12px;border:1px solid var(--border);background:var(--panel2);color:var(--text);padding:0 12px;font:inherit}.btn{border:1px solid #5b4a7a;background:linear-gradient(180deg,#352a4f,#241d35);color:var(--text);border-radius:12px;min-height:46px;padding:0 16px;font-weight:800;cursor:pointer}.btn.danger{background:#48232d;border-color:#7a3848}.btn:disabled{opacity:.45;cursor:not-allowed}.statusline{padding:12px 14px;color:var(--muted);border-bottom:1px solid var(--border)}.statusline strong{color:var(--text)}.scripts{padding:12px}.script{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;padding:12px 14px;margin-bottom:8px;background:var(--panel2);border:1px solid var(--border);border-radius:14px}.script h3{margin:0 0 4px;font-size:.92rem}.script p{margin:0;color:var(--muted);font-size:.72rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.empty{padding:40px;text-align:center;color:var(--muted)}.toast{position:fixed;left:50%;bottom:20px;transform:translate(-50%,20px);opacity:0;background:#2b2340;border:1px solid #5b4a7a;border-radius:12px;padding:11px 16px;z-index:120;transition:.2s}.toast.show{opacity:1;transform:translate(-50%,0)}@media(max-width:700px){.shell{padding:7px}.brand img{width:46px}.brand p{display:none}.nav{gap:5px}.nav a{padding:7px 3px;font-size:.68rem}.tools{grid-template-columns:1fr 1fr}.tools input{grid-column:1/-1}.script{grid-template-columns:1fr}.script .btn{width:100%}}
</style></head><body><div class="shell"><header class="topbar"><div class="brand"><img src="/assets/logo.png" alt="MiSTer Companion"><div><h1>MiSTer Companion Remote</h1><p>Browser remote v3.0.0</p></div></div></header><nav class="nav"><a href="/">Home</a><a href="/controller">Controller</a><a href="/keyboard">Keyboard</a><a href="/games">Games</a><a href="/scripts" class="active">Scripts</a></nav><main class="card"><div class="tools"><input id="search" type="search" placeholder="Search scripts"><button class="btn" id="console">Open console</button><button class="btn danger" id="stop">Stop script</button></div><div class="statusline" id="status">Checking script status...</div><div class="scripts" id="scripts"><div class="empty">Loading scripts...</div></div></main></div><div class="toast"></div><script>
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
        if request_path == "/assets/logo.png" or request_path == "/favicon.ico":
            send_http(sock, "200 OK", "image/png", LOGO_PNG, ["Cache-Control: public, max-age=86400"])
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

    if [ -z "$_pid" ]; then
        return 1
    fi

    if kill -0 "$_pid" 2>/dev/null; then
        return 0
    fi

    return 1
}

daemon_running() {
    _pid="$(pid_value)"

    if process_running_by_pid "$_pid"; then
        return 0
    fi

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