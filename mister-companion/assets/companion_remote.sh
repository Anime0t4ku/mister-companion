#!/bin/sh

TITLE="MiSTer Companion Remote by Anime0t4ku"
SCRIPT_VERSION="2.0.0"
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
import socket
import struct
import subprocess
import sys
import time
import threading
import fcntl

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
HOME_HTML = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover"><meta name="theme-color" content="#120f1c"><title>MiSTer Companion Remote</title><style>\n:root{--bg:#120f1c;--panel:#1b1628;--panel2:#2b2340;--text:#f2ecff;--muted:#b5a9c9;--accent:#8b5cf6;--accent2:#a78bfa;--ok:#39d98a;--danger:#d95768;--border:#3a2f55;--shadow:0 18px 55px rgba(0,0,0,.42)}\n*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html,body{margin:0;min-height:100%;background:radial-gradient(circle at top,#261c3d 0,#120f1c 48%,#0b0911 100%);color:var(--text);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}body{min-height:100dvh}.shell{width:min(1220px,100%);margin:0 auto;padding:16px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 16px;background:rgba(27,22,40,.94);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow);position:relative;z-index:20}.brand{display:flex;align-items:center;gap:12px;min-width:0}.brand img{width:74px;height:auto}.brand-copy{min-width:0}.brand h1{font-size:1rem;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.brand p{margin:3px 0 0;color:var(--muted);font-size:.78rem}.status{display:flex;align-items:center;gap:8px;font-weight:800;font-size:.84rem;white-space:nowrap}.dot{width:10px;height:10px;border-radius:50%;background:#81768f;box-shadow:0 0 0 4px rgba(129,118,143,.12)}.status.connected .dot{background:var(--ok);box-shadow:0 0 0 4px rgba(57,217,138,.13)}.status.disconnected .dot{background:var(--danger);box-shadow:0 0 0 4px rgba(217,87,104,.14)}.nav{display:flex;gap:8px;margin:12px 0}.nav a{flex:1;text-align:center;text-decoration:none;color:var(--text);background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:10px;font-weight:800}.nav a.active,.nav a:hover{background:var(--accent);border-color:var(--accent2)}.card{background:rgba(27,22,40,.96);border:1px solid var(--border);border-radius:22px;box-shadow:var(--shadow)}button{font:inherit;color:inherit}.btn{border:1px solid #5b4a7a;background:linear-gradient(180deg,#352a4f,#241d35);border-radius:14px;min-height:50px;font-weight:900;box-shadow:inset 0 1px rgba(255,255,255,.06),0 5px 14px rgba(0,0,0,.25);cursor:pointer;user-select:none;touch-action:none;transition:transform .06s,background .1s,border-color .1s}.btn.active,.btn:active{transform:translateY(2px) scale(.98);background:var(--accent);border-color:var(--accent2)}.danger{background:#48232d;border-color:#7a3848}.footer{text-align:center;color:var(--muted);font-size:.75rem;padding:14px}.rotate-tip{display:none;position:fixed;inset:0;background:rgba(11,9,17,.94);z-index:100;align-items:center;justify-content:center;padding:24px}.rotate-card{max-width:390px;text-align:center;background:var(--panel);border:1px solid var(--accent);border-radius:22px;padding:26px;box-shadow:var(--shadow)}.rotate-icon{font-size:3rem;margin-bottom:8px}.rotate-card h2{margin:6px 0}.rotate-card p{color:var(--muted);line-height:1.45}.rotate-card .btn{width:100%;margin-top:12px}.toast{position:fixed;left:50%;bottom:20px;transform:translate(-50%,20px);opacity:0;pointer-events:none;background:#2b2340;border:1px solid #5b4a7a;border-radius:12px;padding:11px 16px;z-index:120;transition:.2s;box-shadow:var(--shadow)}.toast.show{opacity:1;transform:translate(-50%,0)}\n@media(max-width:700px){.shell{padding:7px}.topbar{padding:8px 10px;border-radius:14px}.brand img{width:46px}.brand p{display:none}.brand h1{font-size:.82rem}.status{font-size:.7rem}.nav{margin:7px 0;gap:5px}.nav a{padding:7px 4px;font-size:.74rem;border-radius:9px}.footer{display:none}}\n@media(max-width:700px) and (orientation:portrait){.rotate-tip.show{display:flex}}\n\n.home{padding:32px}.hero{text-align:center;max-width:720px;margin:auto}.hero img{width:min(220px,55vw)}.hero h2{font-size:clamp(1.6rem,5vw,2.7rem);margin:8px 0}.hero p{color:var(--muted);line-height:1.55}.choices{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-top:25px}.choice{display:block;text-decoration:none;color:var(--text);padding:24px;border-radius:18px;background:var(--panel2);border:1px solid var(--border);transition:.15s}.choice:hover{transform:translateY(-2px);border-color:var(--accent2)}.choice strong{display:block;font-size:1.18rem;margin-bottom:7px}.choice span{color:var(--muted)}.power{margin-top:20px;padding-top:20px;border-top:1px solid var(--border)}.power h3{margin:0 0 6px}.power p{color:var(--muted);margin:0 0 14px}.power-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.power .soft{background:linear-gradient(180deg,#47366b,#302348);border-color:var(--accent)}.modal{display:none;position:fixed;inset:0;background:rgba(11,9,17,.78);z-index:110;align-items:center;justify-content:center;padding:20px}.modal.show{display:flex}.modal-card{width:min(420px,100%);background:var(--panel);border:1px solid var(--accent);border-radius:20px;padding:22px;box-shadow:var(--shadow)}.modal-card h3{margin-top:0}.modal-card p{color:var(--muted);line-height:1.45}.modal-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:18px}@media(max-width:650px){.home{padding:18px 13px}.choices,.power-grid{grid-template-columns:1fr}.choice{padding:18px}}\n</style></head><body><div class="shell"><header class="topbar"><div class="brand"><img src="/assets/logo.png" alt="MiSTer Companion"><div class="brand-copy"><h1>MiSTer Companion Remote</h1><p>Browser remote v2.0.0</p></div></div><div class="status disconnected"><i class="dot"></i><span>Disconnected</span></div></header><nav class="nav"><a href="/" class="active">Home</a><a href="/controller" class="">Controller</a><a href="/keyboard" class="">Keyboard</a></nav><main class="card home"><div class="hero"><img src="/assets/logo.png" alt="MiSTer Companion logo"><p>Choose the dedicated controller or keyboard interface. Everything runs locally on your MiSTer.</p></div><div class="choices"><a class="choice" href="/controller"><strong>Virtual Controller</strong><span>Responsive gamepad controls optimized for landscape use.</span></a><a class="choice" href="/keyboard"><strong>Virtual Keyboard</strong><span>A full keyboard that scales to the available screen.</span></a></div><section class="power"><h3>Power actions</h3><div class="power-grid"><button class="btn soft" onclick="askPower(\'soft_reboot\',\'Reload Menu\',\'Reload menu.rbf and return to the MiSTer menu?\')">Reload Menu</button><button class="btn danger" onclick="askPower(\'cold_reboot\',\'Reboot\',\'Fully restart the MiSTer? The web remote will disconnect temporarily.\')">Reboot</button></div></section></main><div class="footer">MiSTer Companion Remote by Anime0t4ku</div></div><div class="modal"><div class="modal-card"><h3 class="modal-title"></h3><p class="modal-text"></p><div class="modal-actions"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn danger confirm-power">Confirm</button></div></div></div><div class="toast"></div><script>\nconst state={ws:null,connected:false,held:new Set(),reconnect:null,heartbeat:null,connecting:false};\nfunction wsURL(){const p=location.protocol===\'https:\'?\'wss\':\'ws\';return `${p}://${location.host}/remote/v1`}\nfunction setStatus(ok){state.connected=ok;document.querySelectorAll(\'.status\').forEach(el=>{el.classList.toggle(\'connected\',ok);el.classList.toggle(\'disconnected\',!ok);el.querySelector(\'span\').textContent=ok?\'Connected\':\'Disconnected\'})}\nfunction connect(){clearTimeout(state.reconnect);if(state.connecting||state.ws?.readyState===WebSocket.OPEN||state.ws?.readyState===WebSocket.CONNECTING)return;state.connecting=true;try{state.ws=new WebSocket(wsURL())}catch(e){state.connecting=false;scheduleReconnect();return}state.ws.onopen=()=>{state.connecting=false;setStatus(true);clearInterval(state.heartbeat);state.heartbeat=setInterval(()=>{if(state.ws?.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:"ping"}))},25000)};state.ws.onclose=()=>{state.connecting=false;clearInterval(state.heartbeat);state.heartbeat=null;setStatus(false);releaseVisuals();scheduleReconnect()};state.ws.onerror=()=>setStatus(false)}\nfunction scheduleReconnect(){clearTimeout(state.reconnect);state.reconnect=setTimeout(connect,1500)}\nfunction send(obj){if(state.ws&&state.ws.readyState===WebSocket.OPEN){state.ws.send(JSON.stringify(obj));return true}showToast(\'Remote is disconnected\');return false}\nfunction ctl(name,action){return send({type:\'controller\',control:[\'up\',\'down\',\'left\',\'right\'].includes(name)?\'dpad\':\'button\',name,action})}\nfunction key(name,action){return send({type:\'keyboard\',key:name,action})}\nfunction systemCommand(command){return send({type:\'system\',command})}\nfunction releaseAll(){if(state.ws&&state.ws.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:\'system\',command:\'release_all\'}));releaseVisuals()}\nfunction releaseVisuals(){state.held.clear();document.querySelectorAll(\'.active\').forEach(el=>el.classList.remove(\'active\'))}\nfunction bindHold(selector,callback){document.querySelectorAll(selector).forEach(el=>{const id=el.dataset.name||el.dataset.key;const down=e=>{e.preventDefault();try{el.setPointerCapture(e.pointerId)}catch(_){}if(state.held.has(el))return;state.held.add(el);el.classList.add(\'active\');callback(id,\'down\')};const up=e=>{e.preventDefault();if(!state.held.has(el))return;state.held.delete(el);el.classList.remove(\'active\');callback(id,\'up\')};el.addEventListener(\'pointerdown\',down);[\'pointerup\',\'pointercancel\',\'lostpointercapture\'].forEach(ev=>el.addEventListener(ev,up));el.addEventListener(\'contextmenu\',e=>e.preventDefault())})}\nfunction showToast(message){const t=document.querySelector(\'.toast\');if(!t)return;t.textContent=message;t.classList.add(\'show\');clearTimeout(t._timer);t._timer=setTimeout(()=>t.classList.remove(\'show\'),2400)}\nfunction setupRotateTip(){const tip=document.querySelector(\'.rotate-tip\');if(!tip)return;const update=()=>{const portrait=matchMedia(\'(orientation: portrait)\').matches&&innerWidth<=700;tip.classList.toggle(\'show\',portrait&&!sessionStorage.getItem(\'remotePortraitDismissed\'))};document.querySelector(\'.rotate-dismiss\')?.addEventListener(\'click\',()=>{sessionStorage.setItem(\'remotePortraitDismissed\',\'1\');tip.classList.remove(\'show\')});addEventListener(\'resize\',update);screen.orientation?.addEventListener?.(\'change\',update);update()}\nwindow.addEventListener(\'blur\',releaseAll);document.addEventListener(\'visibilitychange\',()=>{if(document.hidden)releaseAll()});window.addEventListener(\'beforeunload\',releaseAll);document.addEventListener(\'DOMContentLoaded\',()=>{connect();setupRotateTip()});\n\nlet pendingPower=\'\';function askPower(command,title,message){pendingPower=command;document.querySelector(\'.modal-title\').textContent=title;document.querySelector(\'.modal-text\').textContent=message;document.querySelector(\'.modal\').classList.add(\'show\')}function closeModal(){document.querySelector(\'.modal\').classList.remove(\'show\');pendingPower=\'\'}document.querySelector(\'.confirm-power\').addEventListener(\'click\',()=>{const cmd=pendingPower;closeModal();if(systemCommand(cmd))showToast(cmd===\'soft_reboot\'?\'Reloading menu…\':\'Reboot requested…\')});document.querySelector(\'.modal\').addEventListener(\'click\',e=>{if(e.target.classList.contains(\'modal\'))closeModal()});\n</script></body></html>'.encode("utf-8")
CONTROLLER_HTML = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover"><meta name="theme-color" content="#120f1c"><title>Controller · MiSTer Companion Remote</title><style>\n:root{--bg:#120f1c;--panel:#1b1628;--panel2:#2b2340;--text:#f2ecff;--muted:#b5a9c9;--accent:#8b5cf6;--accent2:#a78bfa;--ok:#39d98a;--danger:#d95768;--border:#3a2f55;--shadow:0 18px 55px rgba(0,0,0,.42)}\n*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html,body{margin:0;min-height:100%;background:radial-gradient(circle at top,#261c3d 0,#120f1c 48%,#0b0911 100%);color:var(--text);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}body{min-height:100dvh}.shell{width:min(1220px,100%);margin:0 auto;padding:16px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 16px;background:rgba(27,22,40,.94);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow);position:relative;z-index:20}.brand{display:flex;align-items:center;gap:12px;min-width:0}.brand img{width:74px;height:auto}.brand-copy{min-width:0}.brand h1{font-size:1rem;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.brand p{margin:3px 0 0;color:var(--muted);font-size:.78rem}.status{display:flex;align-items:center;gap:8px;font-weight:800;font-size:.84rem;white-space:nowrap}.dot{width:10px;height:10px;border-radius:50%;background:#81768f;box-shadow:0 0 0 4px rgba(129,118,143,.12)}.status.connected .dot{background:var(--ok);box-shadow:0 0 0 4px rgba(57,217,138,.13)}.status.disconnected .dot{background:var(--danger);box-shadow:0 0 0 4px rgba(217,87,104,.14)}.nav{display:flex;gap:8px;margin:12px 0}.nav a{flex:1;text-align:center;text-decoration:none;color:var(--text);background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:10px;font-weight:800}.nav a.active,.nav a:hover{background:var(--accent);border-color:var(--accent2)}.card{background:rgba(27,22,40,.96);border:1px solid var(--border);border-radius:22px;box-shadow:var(--shadow)}button{font:inherit;color:inherit}.btn{border:1px solid #5b4a7a;background:linear-gradient(180deg,#352a4f,#241d35);border-radius:14px;min-height:50px;font-weight:900;box-shadow:inset 0 1px rgba(255,255,255,.06),0 5px 14px rgba(0,0,0,.25);cursor:pointer;user-select:none;touch-action:none;transition:transform .06s,background .1s,border-color .1s}.btn.active,.btn:active{transform:translateY(2px) scale(.98);background:var(--accent);border-color:var(--accent2)}.danger{background:#48232d;border-color:#7a3848}.footer{text-align:center;color:var(--muted);font-size:.75rem;padding:14px}.rotate-tip{display:none;position:fixed;inset:0;background:rgba(11,9,17,.94);z-index:100;align-items:center;justify-content:center;padding:24px}.rotate-card{max-width:390px;text-align:center;background:var(--panel);border:1px solid var(--accent);border-radius:22px;padding:26px;box-shadow:var(--shadow)}.rotate-icon{font-size:3rem;margin-bottom:8px}.rotate-card h2{margin:6px 0}.rotate-card p{color:var(--muted);line-height:1.45}.rotate-card .btn{width:100%;margin-top:12px}.toast{position:fixed;left:50%;bottom:20px;transform:translate(-50%,20px);opacity:0;pointer-events:none;background:#2b2340;border:1px solid #5b4a7a;border-radius:12px;padding:11px 16px;z-index:120;transition:.2s;box-shadow:var(--shadow)}.toast.show{opacity:1;transform:translate(-50%,0)}\n@media(max-width:700px){.shell{padding:7px}.topbar{padding:8px 10px;border-radius:14px}.brand img{width:46px}.brand p{display:none}.brand h1{font-size:.82rem}.status{font-size:.7rem}.nav{margin:7px 0;gap:5px}.nav a{padding:7px 4px;font-size:.74rem;border-radius:9px}.footer{display:none}}\n@media(max-width:700px) and (orientation:portrait){.rotate-tip.show{display:flex}}\n\n.stage{position:relative;width:100%;overflow:hidden}.scale-box{position:absolute;left:50%;top:0;width:1000px;height:560px;transform-origin:top center;transform:translateX(-50%) scale(var(--ui-scale,1))}.controller-card{width:1000px;height:560px;padding:18px}.shoulders{display:grid;grid-template-columns:1fr 1fr;gap:20px}.shoulders .btn{height:58px}.controller-wrap{display:grid;grid-template-columns:330px 1fr 330px;gap:24px;align-items:center;height:390px}.section-label{text-align:center;color:var(--muted);font-weight:800;font-size:.75rem;letter-spacing:.08em;text-transform:uppercase;margin-bottom:10px}.dpad{display:grid;grid-template-columns:repeat(3,88px);grid-template-rows:repeat(3,88px);justify-content:center}.dpad .btn{border-radius:18px;font-size:1.55rem}.up{grid-column:2}.left{grid-column:1;grid-row:2}.right{grid-column:3;grid-row:2}.down{grid-column:2;grid-row:3}.dpad-center{grid-column:2;grid-row:2;background:#100c18;border:1px solid #302442;border-radius:18px}.center-buttons{display:grid;gap:10px}.center-buttons .btn{height:54px}.face{position:relative;width:280px;height:280px;margin:auto}.face .btn{position:absolute;width:88px;height:88px;border-radius:50%;font-size:1.25rem}.face .x{top:0;left:96px}.face .y{top:96px;left:0}.face .a{top:96px;right:0}.face .b{bottom:0;left:96px}.release{width:100%;height:48px}@media(max-width:700px){.stage{margin-top:0}.scale-box{top:0}}\n</style></head><body><div class="shell"><header class="topbar"><div class="brand"><img src="/assets/logo.png" alt="MiSTer Companion"><div class="brand-copy"><h1>MiSTer Companion Remote</h1><p>Browser remote v2.0.0</p></div></div><div class="status disconnected"><i class="dot"></i><span>Disconnected</span></div></header><nav class="nav"><a href="/" class="">Home</a><a href="/controller" class="active">Controller</a><a href="/keyboard" class="">Keyboard</a></nav><div class="stage"><div class="scale-box"><main class="card controller-card"><div class="shoulders"><button class="btn control" data-name="l">L</button><button class="btn control" data-name="r">R</button></div><div class="controller-wrap"><section><div class="section-label">D-Pad</div><div class="dpad"><button class="btn control up" data-name="up">▲</button><button class="btn control left" data-name="left">◀</button><div class="dpad-center"></div><button class="btn control right" data-name="right">▶</button><button class="btn control down" data-name="down">▼</button></div></section><section><div class="section-label">System</div><div class="center-buttons"><button class="btn control" data-name="select">Select</button><button class="btn control" data-name="home">Home</button><button class="btn control" data-name="start">Start</button></div></section><section><div class="section-label">Buttons</div><div class="face"><button class="btn control x" data-name="x">X</button><button class="btn control y" data-name="y">Y</button><button class="btn control a" data-name="a">A</button><button class="btn control b" data-name="b">B</button></div></section></div><button class="btn danger release" onclick="releaseAll()">Release all inputs</button></main></div></div><div class="footer">MiSTer Companion Remote by Anime0t4ku</div></div><div class="rotate-tip"><div class="rotate-card"><div class="rotate-icon">↻</div><h2>Rotate your phone</h2><p>The remote is designed to use the available screen best in landscape orientation.</p><button class="btn rotate-dismiss">Continue in portrait</button></div></div><div class="toast"></div><script>\nconst state={ws:null,connected:false,held:new Set(),reconnect:null,heartbeat:null,connecting:false};\nfunction wsURL(){const p=location.protocol===\'https:\'?\'wss\':\'ws\';return `${p}://${location.host}/remote/v1`}\nfunction setStatus(ok){state.connected=ok;document.querySelectorAll(\'.status\').forEach(el=>{el.classList.toggle(\'connected\',ok);el.classList.toggle(\'disconnected\',!ok);el.querySelector(\'span\').textContent=ok?\'Connected\':\'Disconnected\'})}\nfunction connect(){clearTimeout(state.reconnect);if(state.connecting||state.ws?.readyState===WebSocket.OPEN||state.ws?.readyState===WebSocket.CONNECTING)return;state.connecting=true;try{state.ws=new WebSocket(wsURL())}catch(e){state.connecting=false;scheduleReconnect();return}state.ws.onopen=()=>{state.connecting=false;setStatus(true);clearInterval(state.heartbeat);state.heartbeat=setInterval(()=>{if(state.ws?.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:"ping"}))},25000)};state.ws.onclose=()=>{state.connecting=false;clearInterval(state.heartbeat);state.heartbeat=null;setStatus(false);releaseVisuals();scheduleReconnect()};state.ws.onerror=()=>setStatus(false)}\nfunction scheduleReconnect(){clearTimeout(state.reconnect);state.reconnect=setTimeout(connect,1500)}\nfunction send(obj){if(state.ws&&state.ws.readyState===WebSocket.OPEN){state.ws.send(JSON.stringify(obj));return true}showToast(\'Remote is disconnected\');return false}\nfunction ctl(name,action){return send({type:\'controller\',control:[\'up\',\'down\',\'left\',\'right\'].includes(name)?\'dpad\':\'button\',name,action})}\nfunction key(name,action){return send({type:\'keyboard\',key:name,action})}\nfunction systemCommand(command){return send({type:\'system\',command})}\nfunction releaseAll(){if(state.ws&&state.ws.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:\'system\',command:\'release_all\'}));releaseVisuals()}\nfunction releaseVisuals(){state.held.clear();document.querySelectorAll(\'.active\').forEach(el=>el.classList.remove(\'active\'))}\nfunction bindHold(selector,callback){document.querySelectorAll(selector).forEach(el=>{const id=el.dataset.name||el.dataset.key;const down=e=>{e.preventDefault();try{el.setPointerCapture(e.pointerId)}catch(_){}if(state.held.has(el))return;state.held.add(el);el.classList.add(\'active\');callback(id,\'down\')};const up=e=>{e.preventDefault();if(!state.held.has(el))return;state.held.delete(el);el.classList.remove(\'active\');callback(id,\'up\')};el.addEventListener(\'pointerdown\',down);[\'pointerup\',\'pointercancel\',\'lostpointercapture\'].forEach(ev=>el.addEventListener(ev,up));el.addEventListener(\'contextmenu\',e=>e.preventDefault())})}\nfunction showToast(message){const t=document.querySelector(\'.toast\');if(!t)return;t.textContent=message;t.classList.add(\'show\');clearTimeout(t._timer);t._timer=setTimeout(()=>t.classList.remove(\'show\'),2400)}\nfunction setupRotateTip(){const tip=document.querySelector(\'.rotate-tip\');if(!tip)return;const update=()=>{const portrait=matchMedia(\'(orientation: portrait)\').matches&&innerWidth<=700;tip.classList.toggle(\'show\',portrait&&!sessionStorage.getItem(\'remotePortraitDismissed\'))};document.querySelector(\'.rotate-dismiss\')?.addEventListener(\'click\',()=>{sessionStorage.setItem(\'remotePortraitDismissed\',\'1\');tip.classList.remove(\'show\')});addEventListener(\'resize\',update);screen.orientation?.addEventListener?.(\'change\',update);update()}\nwindow.addEventListener(\'blur\',releaseAll);document.addEventListener(\'visibilitychange\',()=>{if(document.hidden)releaseAll()});window.addEventListener(\'beforeunload\',releaseAll);document.addEventListener(\'DOMContentLoaded\',()=>{connect();setupRotateTip()});\n\nfunction fitUI(){const stage=document.querySelector(\'.stage\');if(!stage)return;const vv=window.visualViewport;const vh=vv?vv.height:innerHeight;const top=stage.getBoundingClientRect().top-(vv?vv.offsetTop:0);const aw=Math.max(240,stage.clientWidth);const ah=Math.max(180,vh-top-6);const scale=Math.min(aw/1000,ah/560,1.18);document.documentElement.style.setProperty(\'--ui-scale\',scale);stage.style.height=(560*scale)+\'px\'}document.addEventListener(\'DOMContentLoaded\',()=>{bindHold(\'.control\',ctl);fitUI()});addEventListener(\'resize\',fitUI);visualViewport?.addEventListener(\'resize\',fitUI);screen.orientation?.addEventListener?.(\'change\',()=>setTimeout(fitUI,80));\n</script></body></html>'.encode("utf-8")
KEYBOARD_HTML = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover"><meta name="theme-color" content="#120f1c"><title>Keyboard · MiSTer Companion Remote</title><style>\n:root{--bg:#120f1c;--panel:#1b1628;--panel2:#2b2340;--text:#f2ecff;--muted:#b5a9c9;--accent:#8b5cf6;--accent2:#a78bfa;--ok:#39d98a;--danger:#d95768;--border:#3a2f55;--shadow:0 18px 55px rgba(0,0,0,.42)}\n*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html,body{margin:0;min-height:100%;background:radial-gradient(circle at top,#261c3d 0,#120f1c 48%,#0b0911 100%);color:var(--text);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}body{min-height:100dvh}.shell{width:min(1220px,100%);margin:0 auto;padding:16px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 16px;background:rgba(27,22,40,.94);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow);position:relative;z-index:20}.brand{display:flex;align-items:center;gap:12px;min-width:0}.brand img{width:74px;height:auto}.brand-copy{min-width:0}.brand h1{font-size:1rem;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.brand p{margin:3px 0 0;color:var(--muted);font-size:.78rem}.status{display:flex;align-items:center;gap:8px;font-weight:800;font-size:.84rem;white-space:nowrap}.dot{width:10px;height:10px;border-radius:50%;background:#81768f;box-shadow:0 0 0 4px rgba(129,118,143,.12)}.status.connected .dot{background:var(--ok);box-shadow:0 0 0 4px rgba(57,217,138,.13)}.status.disconnected .dot{background:var(--danger);box-shadow:0 0 0 4px rgba(217,87,104,.14)}.nav{display:flex;gap:8px;margin:12px 0}.nav a{flex:1;text-align:center;text-decoration:none;color:var(--text);background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:10px;font-weight:800}.nav a.active,.nav a:hover{background:var(--accent);border-color:var(--accent2)}.card{background:rgba(27,22,40,.96);border:1px solid var(--border);border-radius:22px;box-shadow:var(--shadow)}button{font:inherit;color:inherit}.btn{border:1px solid #5b4a7a;background:linear-gradient(180deg,#352a4f,#241d35);border-radius:14px;min-height:50px;font-weight:900;box-shadow:inset 0 1px rgba(255,255,255,.06),0 5px 14px rgba(0,0,0,.25);cursor:pointer;user-select:none;touch-action:none;transition:transform .06s,background .1s,border-color .1s}.btn.active,.btn:active{transform:translateY(2px) scale(.98);background:var(--accent);border-color:var(--accent2)}.danger{background:#48232d;border-color:#7a3848}.footer{text-align:center;color:var(--muted);font-size:.75rem;padding:14px}.rotate-tip{display:none;position:fixed;inset:0;background:rgba(11,9,17,.94);z-index:100;align-items:center;justify-content:center;padding:24px}.rotate-card{max-width:390px;text-align:center;background:var(--panel);border:1px solid var(--accent);border-radius:22px;padding:26px;box-shadow:var(--shadow)}.rotate-icon{font-size:3rem;margin-bottom:8px}.rotate-card h2{margin:6px 0}.rotate-card p{color:var(--muted);line-height:1.45}.rotate-card .btn{width:100%;margin-top:12px}.toast{position:fixed;left:50%;bottom:20px;transform:translate(-50%,20px);opacity:0;pointer-events:none;background:#2b2340;border:1px solid #5b4a7a;border-radius:12px;padding:11px 16px;z-index:120;transition:.2s;box-shadow:var(--shadow)}.toast.show{opacity:1;transform:translate(-50%,0)}\n@media(max-width:700px){.shell{padding:7px}.topbar{padding:8px 10px;border-radius:14px}.brand img{width:46px}.brand p{display:none}.brand h1{font-size:.82rem}.status{font-size:.7rem}.nav{margin:7px 0;gap:5px}.nav a{padding:7px 4px;font-size:.74rem;border-radius:9px}.footer{display:none}}\n@media(max-width:700px) and (orientation:portrait){.rotate-tip.show{display:flex}}\n\n.stage{position:relative;width:100%;overflow:hidden}.scale-box{position:absolute;left:50%;top:0;width:1180px;height:520px;transform-origin:top center;transform:translateX(-50%) scale(var(--ui-scale,1))}.keyboard-card{width:1180px;height:520px;padding:14px}.keyboard-tools{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.keyboard-tools h2{margin:0;font-size:1.05rem}.keyboard-tools .btn{min-height:38px;padding:0 14px}.key-row{display:flex;gap:5px;margin-bottom:5px}.key{flex:var(--w,1);min-width:0;height:53px;border-radius:9px;font-size:.78rem;padding:0 3px}.bottom{display:grid;grid-template-columns:1fr 230px;gap:10px}.nav-cluster{display:grid;grid-template-columns:repeat(6,1fr);gap:5px}.nav-cluster .key{height:44px}.arrows{display:grid;grid-template-columns:repeat(3,1fr);grid-template-rows:repeat(2,44px);gap:5px}.arrows .key{height:44px}.au{grid-column:2}.al{grid-column:1;grid-row:2}.ad{grid-column:2;grid-row:2}.ar{grid-column:3;grid-row:2}\n</style></head><body><div class="shell"><header class="topbar"><div class="brand"><img src="/assets/logo.png" alt="MiSTer Companion"><div class="brand-copy"><h1>MiSTer Companion Remote</h1><p>Browser remote v2.0.0</p></div></div><div class="status disconnected"><i class="dot"></i><span>Disconnected</span></div></header><nav class="nav"><a href="/" class="">Home</a><a href="/controller" class="">Controller</a><a href="/keyboard" class="active">Keyboard</a></nav><div class="stage"><div class="scale-box"><main class="card keyboard-card"><div class="keyboard-tools"><h2>Virtual Keyboard</h2><button class="btn danger" onclick="releaseAll()">Release all inputs</button></div><div class="key-row"><button class="btn key" style="--w:1" data-key="KEY_ESC">Esc</button><button class="btn key" style="--w:1" data-key="KEY_F1">F1</button><button class="btn key" style="--w:1" data-key="KEY_F2">F2</button><button class="btn key" style="--w:1" data-key="KEY_F3">F3</button><button class="btn key" style="--w:1" data-key="KEY_F4">F4</button><button class="btn key" style="--w:1" data-key="KEY_F5">F5</button><button class="btn key" style="--w:1" data-key="KEY_F6">F6</button><button class="btn key" style="--w:1" data-key="KEY_F7">F7</button><button class="btn key" style="--w:1" data-key="KEY_F8">F8</button><button class="btn key" style="--w:1" data-key="KEY_F9">F9</button><button class="btn key" style="--w:1" data-key="KEY_F10">F10</button><button class="btn key" style="--w:1" data-key="KEY_F11">F11</button><button class="btn key" style="--w:1" data-key="KEY_F12">F12</button></div><div class="key-row"><button class="btn key" style="--w:1" data-key="KEY_GRAVE">`</button><button class="btn key" style="--w:1" data-key="KEY_1">1</button><button class="btn key" style="--w:1" data-key="KEY_2">2</button><button class="btn key" style="--w:1" data-key="KEY_3">3</button><button class="btn key" style="--w:1" data-key="KEY_4">4</button><button class="btn key" style="--w:1" data-key="KEY_5">5</button><button class="btn key" style="--w:1" data-key="KEY_6">6</button><button class="btn key" style="--w:1" data-key="KEY_7">7</button><button class="btn key" style="--w:1" data-key="KEY_8">8</button><button class="btn key" style="--w:1" data-key="KEY_9">9</button><button class="btn key" style="--w:1" data-key="KEY_0">0</button><button class="btn key" style="--w:1" data-key="KEY_MINUS">-</button><button class="btn key" style="--w:1" data-key="KEY_EQUAL">=</button><button class="btn key" style="--w:2" data-key="KEY_BACKSPACE">Backspace</button></div><div class="key-row"><button class="btn key" style="--w:1.5" data-key="KEY_TAB">Tab</button><button class="btn key" style="--w:1" data-key="KEY_Q">Q</button><button class="btn key" style="--w:1" data-key="KEY_W">W</button><button class="btn key" style="--w:1" data-key="KEY_E">E</button><button class="btn key" style="--w:1" data-key="KEY_R">R</button><button class="btn key" style="--w:1" data-key="KEY_T">T</button><button class="btn key" style="--w:1" data-key="KEY_Y">Y</button><button class="btn key" style="--w:1" data-key="KEY_U">U</button><button class="btn key" style="--w:1" data-key="KEY_I">I</button><button class="btn key" style="--w:1" data-key="KEY_O">O</button><button class="btn key" style="--w:1" data-key="KEY_P">P</button><button class="btn key" style="--w:1" data-key="KEY_LEFTBRACE">[</button><button class="btn key" style="--w:1" data-key="KEY_RIGHTBRACE">]</button><button class="btn key" style="--w:1.5" data-key="KEY_BACKSLASH">\\</button></div><div class="key-row"><button class="btn key" style="--w:1.7" data-key="KEY_CAPSLOCK">Caps</button><button class="btn key" style="--w:1" data-key="KEY_A">A</button><button class="btn key" style="--w:1" data-key="KEY_S">S</button><button class="btn key" style="--w:1" data-key="KEY_D">D</button><button class="btn key" style="--w:1" data-key="KEY_F">F</button><button class="btn key" style="--w:1" data-key="KEY_G">G</button><button class="btn key" style="--w:1" data-key="KEY_H">H</button><button class="btn key" style="--w:1" data-key="KEY_J">J</button><button class="btn key" style="--w:1" data-key="KEY_K">K</button><button class="btn key" style="--w:1" data-key="KEY_L">L</button><button class="btn key" style="--w:1" data-key="KEY_SEMICOLON">;</button><button class="btn key" style="--w:1" data-key="KEY_APOSTROPHE">\'</button><button class="btn key" style="--w:2.3" data-key="KEY_ENTER">Enter</button></div><div class="key-row"><button class="btn key" style="--w:2.2" data-key="KEY_LEFTSHIFT">Shift</button><button class="btn key" style="--w:1" data-key="KEY_Z">Z</button><button class="btn key" style="--w:1" data-key="KEY_X">X</button><button class="btn key" style="--w:1" data-key="KEY_C">C</button><button class="btn key" style="--w:1" data-key="KEY_V">V</button><button class="btn key" style="--w:1" data-key="KEY_B">B</button><button class="btn key" style="--w:1" data-key="KEY_N">N</button><button class="btn key" style="--w:1" data-key="KEY_M">M</button><button class="btn key" style="--w:1" data-key="KEY_COMMA">,</button><button class="btn key" style="--w:1" data-key="KEY_DOT">.</button><button class="btn key" style="--w:1" data-key="KEY_SLASH">/</button><button class="btn key" style="--w:2.6" data-key="KEY_RIGHTSHIFT">Shift</button></div><div class="key-row"><button class="btn key" style="--w:1.5" data-key="KEY_LEFTCTRL">Ctrl</button><button class="btn key" style="--w:1.5" data-key="KEY_LEFTALT">Alt</button><button class="btn key" style="--w:7" data-key="KEY_SPACE">Space</button><button class="btn key" style="--w:1.5" data-key="KEY_RIGHTALT">Alt</button><button class="btn key" style="--w:1.5" data-key="KEY_RIGHTCTRL">Ctrl</button></div><div class="bottom"><div class="nav-cluster"><button class="btn key" data-key="KEY_INSERT">Ins</button><button class="btn key" data-key="KEY_DELETE">Del</button><button class="btn key" data-key="KEY_HOME">Home</button><button class="btn key" data-key="KEY_END">End</button><button class="btn key" data-key="KEY_PAGEUP">PgUp</button><button class="btn key" data-key="KEY_PAGEDOWN">PgDn</button></div><div class="arrows"><button class="btn key au" data-key="KEY_UP">▲</button><button class="btn key al" data-key="KEY_LEFT">◀</button><button class="btn key ad" data-key="KEY_DOWN">▼</button><button class="btn key ar" data-key="KEY_RIGHT">▶</button></div></div></main></div></div><div class="footer">MiSTer Companion Remote by Anime0t4ku</div></div><div class="rotate-tip"><div class="rotate-card"><div class="rotate-icon">↻</div><h2>Rotate your phone</h2><p>The remote is designed to use the available screen best in landscape orientation.</p><button class="btn rotate-dismiss">Continue in portrait</button></div></div><div class="toast"></div><script>\nconst state={ws:null,connected:false,held:new Set(),reconnect:null,heartbeat:null,connecting:false};\nfunction wsURL(){const p=location.protocol===\'https:\'?\'wss\':\'ws\';return `${p}://${location.host}/remote/v1`}\nfunction setStatus(ok){state.connected=ok;document.querySelectorAll(\'.status\').forEach(el=>{el.classList.toggle(\'connected\',ok);el.classList.toggle(\'disconnected\',!ok);el.querySelector(\'span\').textContent=ok?\'Connected\':\'Disconnected\'})}\nfunction connect(){clearTimeout(state.reconnect);if(state.connecting||state.ws?.readyState===WebSocket.OPEN||state.ws?.readyState===WebSocket.CONNECTING)return;state.connecting=true;try{state.ws=new WebSocket(wsURL())}catch(e){state.connecting=false;scheduleReconnect();return}state.ws.onopen=()=>{state.connecting=false;setStatus(true);clearInterval(state.heartbeat);state.heartbeat=setInterval(()=>{if(state.ws?.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:"ping"}))},25000)};state.ws.onclose=()=>{state.connecting=false;clearInterval(state.heartbeat);state.heartbeat=null;setStatus(false);releaseVisuals();scheduleReconnect()};state.ws.onerror=()=>setStatus(false)}\nfunction scheduleReconnect(){clearTimeout(state.reconnect);state.reconnect=setTimeout(connect,1500)}\nfunction send(obj){if(state.ws&&state.ws.readyState===WebSocket.OPEN){state.ws.send(JSON.stringify(obj));return true}showToast(\'Remote is disconnected\');return false}\nfunction ctl(name,action){return send({type:\'controller\',control:[\'up\',\'down\',\'left\',\'right\'].includes(name)?\'dpad\':\'button\',name,action})}\nfunction key(name,action){return send({type:\'keyboard\',key:name,action})}\nfunction systemCommand(command){return send({type:\'system\',command})}\nfunction releaseAll(){if(state.ws&&state.ws.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:\'system\',command:\'release_all\'}));releaseVisuals()}\nfunction releaseVisuals(){state.held.clear();document.querySelectorAll(\'.active\').forEach(el=>el.classList.remove(\'active\'))}\nfunction bindHold(selector,callback){document.querySelectorAll(selector).forEach(el=>{const id=el.dataset.name||el.dataset.key;const down=e=>{e.preventDefault();try{el.setPointerCapture(e.pointerId)}catch(_){}if(state.held.has(el))return;state.held.add(el);el.classList.add(\'active\');callback(id,\'down\')};const up=e=>{e.preventDefault();if(!state.held.has(el))return;state.held.delete(el);el.classList.remove(\'active\');callback(id,\'up\')};el.addEventListener(\'pointerdown\',down);[\'pointerup\',\'pointercancel\',\'lostpointercapture\'].forEach(ev=>el.addEventListener(ev,up));el.addEventListener(\'contextmenu\',e=>e.preventDefault())})}\nfunction showToast(message){const t=document.querySelector(\'.toast\');if(!t)return;t.textContent=message;t.classList.add(\'show\');clearTimeout(t._timer);t._timer=setTimeout(()=>t.classList.remove(\'show\'),2400)}\nfunction setupRotateTip(){const tip=document.querySelector(\'.rotate-tip\');if(!tip)return;const update=()=>{const portrait=matchMedia(\'(orientation: portrait)\').matches&&innerWidth<=700;tip.classList.toggle(\'show\',portrait&&!sessionStorage.getItem(\'remotePortraitDismissed\'))};document.querySelector(\'.rotate-dismiss\')?.addEventListener(\'click\',()=>{sessionStorage.setItem(\'remotePortraitDismissed\',\'1\');tip.classList.remove(\'show\')});addEventListener(\'resize\',update);screen.orientation?.addEventListener?.(\'change\',update);update()}\nwindow.addEventListener(\'blur\',releaseAll);document.addEventListener(\'visibilitychange\',()=>{if(document.hidden)releaseAll()});window.addEventListener(\'beforeunload\',releaseAll);document.addEventListener(\'DOMContentLoaded\',()=>{connect();setupRotateTip()});\n\nconst browserMap={Escape:\'KEY_ESC\',Backspace:\'KEY_BACKSPACE\',Tab:\'KEY_TAB\',Enter:\'KEY_ENTER\',ShiftLeft:\'KEY_LEFTSHIFT\',ShiftRight:\'KEY_RIGHTSHIFT\',ControlLeft:\'KEY_LEFTCTRL\',ControlRight:\'KEY_RIGHTCTRL\',AltLeft:\'KEY_LEFTALT\',AltRight:\'KEY_RIGHTALT\',Space:\'KEY_SPACE\',CapsLock:\'KEY_CAPSLOCK\',ArrowUp:\'KEY_UP\',ArrowDown:\'KEY_DOWN\',ArrowLeft:\'KEY_LEFT\',ArrowRight:\'KEY_RIGHT\',Home:\'KEY_HOME\',End:\'KEY_END\',PageUp:\'KEY_PAGEUP\',PageDown:\'KEY_PAGEDOWN\',Insert:\'KEY_INSERT\',Delete:\'KEY_DELETE\'};for(let i=1;i<=12;i++)browserMap[\'F\'+i]=\'KEY_F\'+i;for(let i=0;i<=9;i++)browserMap[\'Digit\'+i]=\'KEY_\'+i;for(const c of \'ABCDEFGHIJKLMNOPQRSTUVWXYZ\')browserMap[\'Key\'+c]=\'KEY_\'+c;Object.assign(browserMap,{Minus:\'KEY_MINUS\',Equal:\'KEY_EQUAL\',BracketLeft:\'KEY_LEFTBRACE\',BracketRight:\'KEY_RIGHTBRACE\',Backslash:\'KEY_BACKSLASH\',Semicolon:\'KEY_SEMICOLON\',Quote:\'KEY_APOSTROPHE\',Backquote:\'KEY_GRAVE\',Comma:\'KEY_COMMA\',Period:\'KEY_DOT\',Slash:\'KEY_SLASH\'});const physicalHeld=new Set();function fitUI(){const stage=document.querySelector(\'.stage\');if(!stage)return;const vv=window.visualViewport;const vh=vv?vv.height:innerHeight;const top=stage.getBoundingClientRect().top-(vv?vv.offsetTop:0);const aw=Math.max(260,stage.clientWidth);const ah=Math.max(180,vh-top-6);const scale=Math.min(aw/1180,ah/520,1);document.documentElement.style.setProperty(\'--ui-scale\',scale);stage.style.height=(520*scale)+\'px\'}document.addEventListener(\'DOMContentLoaded\',()=>{bindHold(\'.key\',key);fitUI()});addEventListener(\'resize\',fitUI);visualViewport?.addEventListener(\'resize\',fitUI);screen.orientation?.addEventListener?.(\'change\',()=>setTimeout(fitUI,80));window.addEventListener(\'keydown\',e=>{const k=browserMap[e.code];if(!k||physicalHeld.has(k))return;e.preventDefault();physicalHeld.add(k);key(k,\'down\')});window.addEventListener(\'keyup\',e=>{const k=browserMap[e.code];if(!k)return;e.preventDefault();physicalHeld.delete(k);key(k,\'up\')});window.addEventListener(\'blur\',()=>physicalHeld.clear());\n</script></body></html>'.encode("utf-8")


def send_http(sock, status, content_type, body, extra_headers=None):
    if isinstance(body, str):
        body = body.encode("utf-8")
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
    sock.sendall(("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + body)



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


def response(ok=True, response_type="result", message="", version=DAEMON_VERSION):
    return {
        "ok": ok,
        "type": response_type,
        "message": message,
        "version": version,
    }


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


def handle_client(sock, address, path):
    try:
        request = sock.recv(4096).decode("iso-8859-1", errors="ignore")

        if not request:
            return

        lines = request.split("\r\n")
        request_line = lines[0].split()

        if len(request_line) < 2:
            return

        request_path = request_line[1].split("?")[0]

        if request_path == "/status":
            body = json.dumps(response(True, "status", "MiSTer Companion Remote daemon is running")).encode("utf-8")
            send_http(sock, "200 OK", "application/json; charset=utf-8", body)
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

        if request_path == "/assets/logo.png":
            send_http(sock, "200 OK", "image/png", LOGO_PNG, ["Cache-Control: public, max-age=86400"])
            return

        if request_path == "/favicon.ico":
            send_http(sock, "200 OK", "image/png", LOGO_PNG, ["Cache-Control: public, max-age=86400"])
            return

        if request_path != path:
            send_http(sock, "404 Not Found", "text/plain; charset=utf-8", b"Not found")
            return

        headers = {}

        for line in lines[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.lower().strip()] = value.strip()

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

        # The short timeout is only for the initial HTTP/WebSocket handshake.
        # Once upgraded, keep healthy idle WebSocket connections open.
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
                # Pong frame
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