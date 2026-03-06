import requests
import math
import os
import json
from datetime import datetime
from pathlib import Path

# ── CONFIG ──────────────────────────────────────────────
LAT      = -34.83
LON      = -57.98
WIND_MIN = 10  # nudos mínimos
OFFSET_FILE = "last_update_id.json"

# ── CLIMA ───────────────────────────────────────────────
def get_weather():
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        f"&current=temperature_2m,apparent_temperature,wind_speed_10m,wind_direction_10m"
        f"&wind_speed_unit=kn"
        f"&timezone=America%2FArgentina%2FBuenos_Aires"
    )
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    return res.json()["current"]

def deg_to_compass(deg):
    dirs = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSO','SO','OSO','O','ONO','NO','NNO']
    return dirs[round(deg / 22.5) % 16]

def is_good_direction(deg):
    # Malo: S, SO, O (170°-280°)
    return not (170 <= deg <= 280)

def get_tide(hour):
    t = hour / 24
    tide = 0.6 + 0.5 * math.sin(2 * math.pi * t * 3.9 - 1.2) \
               + 0.15 * math.sin(2 * math.pi * t * 7.8 + 0.5)
    return max(0.05, tide)

def is_tide_low(level):
    return level < 0.55

# ── TELEGRAM ────────────────────────────────────────────
def send_telegram(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    res = requests.post(url, json=payload, timeout=10)
    res.raise_for_status()
    return res.json()

def get_updates(token, offset=0):
    url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=3"
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    return res.json().get("result", [])

def load_offset():
    if Path(OFFSET_FILE).exists():
        with open(OFFSET_FILE) as f:
            return json.load(f).get("offset", 0)
    return 0

def save_offset(offset):
    with open(OFFSET_FILE, "w") as f:
        json.dump({"offset": offset}, f)

# ── MENSAJES ────────────────────────────────────────────
def build_status_msg(wind, dir_comp, deg, tide, temp, feels, all_good, wind_ok, dir_ok, tide_ok):
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    header = "🪁 ¡SÍ, ES ÓPTIMO PARA NAVEGAR!" if all_good else "🚫 No es óptimo por ahora."
    return (
        f"{header}\n\n"
        f"{'✅' if wind_ok else '❌'} Viento: {wind:.1f} kn {'(OK)' if wind_ok else f'(necesitás ≥{WIND_MIN} kn)'}\n"
        f"{'✅' if dir_ok else '❌'} Dirección: {dir_comp} ({deg}°) {'(OK)' if dir_ok else '(S/SO/O: no apto)'}\n"
        f"{'✅' if tide_ok else '❌'} Marea: {tide:.2f}m {'(baja ✓)' if tide_ok else '(alta, esperá que baje)'}\n"
        f"🌡 Temperatura: {temp:.0f}°C (sensación {feels:.0f}°C)\n\n"
        f"🕐 {now_str}"
    )

def build_optimal_msg(wind, dir_comp, deg, tide, temp, feels):
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    return (
        f"🪁 KITE MONITOR — PUNTA LARA\n\n"
        f"✅ ¡CONDICIONES ÓPTIMAS!\n\n"
        f"🌬 Viento: {wind:.1f} nudos\n"
        f"🧭 Dirección: {dir_comp} ({deg}°)\n"
        f"🌊 Marea: {tide:.2f}m (baja)\n"
        f"🌡 Temperatura: {temp:.0f}°C (sensación {feels:.0f}°C)\n\n"
        f"¡Es momento de salir a kitesurf! 🏄\n\n"
        f"🕐 {now_str}"
    )

# ── MAIN ────────────────────────────────────────────────
def main():
    token   = os.environ["TG_TOKEN"]
    chat_id = os.environ["TG_CHAT_ID"]

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Chequeando condiciones...")

    # Obtener clima
    data     = get_weather()
    wind     = data["wind_speed_10m"]
    deg      = data["wind_direction_10m"]
    temp     = data["temperature_2m"]
    feels    = data["apparent_temperature"]
    hour     = datetime.now().hour
    tide     = get_tide(hour)
    dir_comp = deg_to_compass(deg)

    wind_ok  = wind >= WIND_MIN
    dir_ok   = is_good_direction(deg)
    tide_ok  = is_tide_low(tide)
    all_good = wind_ok and dir_ok and tide_ok

    print(f"  Viento: {wind:.1f} kn ({dir_comp} {deg}°) → {'✅' if wind_ok else '❌'} velocidad, {'✅' if dir_ok else '❌'} dirección")
    print(f"  Marea:  {tide:.2f}m → {'✅' if tide_ok else '❌'}")
    print(f"  Resultado: {'¡ÓPTIMO!' if all_good else 'No apto'}")

    # ── Responder mensajes nuevos del usuario ────────────
    print("  Revisando mensajes nuevos en Telegram...")
    try:
        offset = load_offset()
        updates = get_updates(token, offset)

        for update in updates:
            update_id = update.get("update_id", 0)
            msg_text  = update.get("message", {}).get("text", "").strip()
            from_chat = update.get("message", {}).get("chat", {}).get("id")

            if from_chat and msg_text:
                reply = build_status_msg(wind, dir_comp, deg, tide, temp, feels,
                                         all_good, wind_ok, dir_ok, tide_ok)
                send_telegram(token, str(from_chat), reply)
                print(f"  📨 Respondido mensaje: '{msg_text}'")

            # Guardar el offset para no repetir mensajes
            save_offset(update_id + 1)

    except Exception as e:
        print(f"  ⚠️ Error revisando mensajes: {e}")

    # ── Alerta automática SOLO si condiciones óptimas ────
    if all_good:
        msg = build_optimal_msg(wind, dir_comp, deg, tide, temp, feels)
        result = send_telegram(token, chat_id, msg)
        if result.get("ok"):
            print("  📨 Alerta automática enviada!")
        else:
            print(f"  ❌ Error Telegram: {result}")
    else:
        print("  Sin alerta automática — condiciones no óptimas.")

if __name__ == "__main__":
    main()
