import requests
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────
LAT = -34.83
LON = -57.98
WIND_MIN = 10  # nudos mínimos

# ── FUNCIONES ───────────────────────────────────────────
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
    # Malo: S (170-190), SO (190-250), O (250-280)
    return not (170 <= deg <= 280)

def get_tide(hour):
    import math
    t = hour / 24
    tide = 0.6 + 0.5 * math.sin(2 * math.pi * t * 3.9 - 1.2) \
               + 0.15 * math.sin(2 * math.pi * t * 7.8 + 0.5)
    return max(0.05, tide)

def is_tide_low(level):
    return level < 0.55

def send_telegram(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    res = requests.post(url, json=payload, timeout=10)
    res.raise_for_status()
    return res.json()

# ── MAIN ────────────────────────────────────────────────
def main():
    import os

    token   = os.environ["TG_TOKEN"]
    chat_id = os.environ["TG_CHAT_ID"]

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Chequeando condiciones...")

    data     = get_weather()
    wind     = data["wind_speed_10m"]
    deg      = data["wind_direction_10m"]
    temp     = data["temperature_2m"]
    feels    = data["apparent_temperature"]
    hour     = datetime.now().hour
    tide     = get_tide(hour)
    dir_comp = deg_to_compass(deg)

    wind_ok = wind >= WIND_MIN
    dir_ok  = is_good_direction(deg)
    tide_ok = is_tide_low(tide)
    all_good = wind_ok and dir_ok and tide_ok

    print(f"  Viento: {wind:.1f} kn ({dir_comp} {deg}°) → {'✅' if wind_ok else '❌'} velocidad, {'✅' if dir_ok else '❌'} dirección")
    print(f"  Marea:  {tide:.2f}m → {'✅' if tide_ok else '❌'}")
    print(f"  Resultado: {'¡ÓPTIMO!' if all_good else 'No apto'}")

    if all_good:
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        msg = (
            f"🪁 KITE MONITOR — PUNTA LARA\n\n"
            f"✅ ¡CONDICIONES ÓPTIMAS!\n\n"
            f"🌬 Viento: {wind:.1f} nudos\n"
            f"🧭 Dirección: {dir_comp} ({deg}°)\n"
            f"🌊 Marea: {tide:.2f}m (baja)\n"
            f"🌡 Temperatura: {temp:.0f}°C (sensación {feels:.0f}°C)\n\n"
            f"¡Es momento de salir a kitesurf! 🏄\n\n"
            f"🕐 {now_str}"
        )
        result = send_telegram(token, chat_id, msg)
        if result.get("ok"):
            print("  📨 Mensaje enviado a Telegram!")
        else:
            print(f"  ❌ Error Telegram: {result}")
    else:
        print("  Sin alerta — condiciones no óptimas.")

if __name__ == "__main__":
    main()
