import requests
import math
import os
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────
LAT      = -34.83
LON      = -57.98
WIND_MIN = 10  # nudos mínimos

# ── CLIMA ───────────────────────────────────────────────
def get_weather():
    # Usamos wind_speed_80m para mayor precisión (más cercano a lo que se siente en el agua)
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        f"&current=temperature_2m,apparent_temperature,wind_speed_10m,wind_direction_10m"
        f"&hourly=wind_speed_80m,wind_direction_80m"
        f"&wind_speed_unit=kn"
        f"&timezone=America%2FArgentina%2FBuenos_Aires"
        f"&forecast_days=1"
    )
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    data = res.json()

    # Tomar el viento a 80m de la hora actual (más preciso para kite)
    hour_now = datetime.now().hour
    wind_80m = data["hourly"]["wind_speed_80m"][hour_now]
    dir_80m  = data["hourly"]["wind_direction_80m"][hour_now]

    current = data["current"]
    current["wind_speed_10m"]     = wind_80m  # reemplazamos con el dato mejor
    current["wind_direction_10m"] = dir_80m

    return current

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

def get_updates(token):
    # Solo trae mensajes de los últimos 30 minutos para no responder mensajes viejos
    url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=3&allowed_updates=[\"message\"]"
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    updates = res.json().get("result", [])

    # Filtrar solo mensajes de los últimos 30 minutos
    now_ts = datetime.now().timestamp()
    recent = [u for u in updates if now_ts - u.get("message", {}).get("date", 0) <= 1800]
    return recent

def confirm_read(token, updates):
    # Marcar todos los mensajes como leídos para no repetirlos
    if not updates:
        return
    last_id = max(u["update_id"] for u in updates)
    url = f"https://api.telegram.org/bot{token}/getUpdates?offset={last_id + 1}&timeout=1"
    try:
        requests.get(url, timeout=5)
    except:
        pass

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

    print(f"  Viento (80m): {wind:.1f} kn ({dir_comp} {deg}°) → {'✅' if wind_ok else '❌'} velocidad, {'✅' if dir_ok else '❌'} dirección")
    print(f"  Marea:  {tide:.2f}m → {'✅' if tide_ok else '❌'}")
    print(f"  Resultado: {'¡ÓPTIMO!' if all_good else 'No apto'}")

    # ── Responder mensajes nuevos del usuario ────────────
    print("  Revisando mensajes nuevos en Telegram...")
    try:
        updates = get_updates(token)
        if updates:
            for update in updates:
                msg_text  = update.get("message", {}).get("text", "").strip()
                from_chat = update.get("message", {}).get("chat", {}).get("id")
                if from_chat and msg_text:
                    reply = build_status_msg(wind, dir_comp, deg, tide, temp, feels,
                                             all_good, wind_ok, dir_ok, tide_ok)
                    send_telegram(token, str(from_chat), reply)
                    print(f"  📨 Respondido: '{msg_text}'")
            # Marcar como leídos para no repetir en el próximo ciclo
            confirm_read(token, updates)
        else:
            print("  Sin mensajes nuevos.")
    except Exception as e:
        print(f"  ⚠️ Error revisando mensajes: {e}")

    # ── Alerta automática SOLO si todas las condiciones son óptimas ────
    if all_good:
        msg = build_optimal_msg(wind, dir_comp, deg, tide, temp, feels)
        result = send_telegram(token, chat_id, msg)
        if result.get("ok"):
            print("  📨 Alerta automática enviada!")
        else:
            print(f"  ❌ Error Telegram: {result}")
    else:
        print("  Sin alerta — condiciones no óptimas.")

if __name__ == "__main__":
    main()
