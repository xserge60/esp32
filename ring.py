import time
import network
import urequests
from machine import Pin

# === 1. НАЛАШТУВАННЯ WI-FI ===
WIFI_SSID = "MikroTik2"
WIFI_PASS = "chukhnovskogo"

# Адреса твого сервера/скрипта на Raspberry Pi (або Telegram Bot Webhook)
# Наприклад: "http://192.168.88.50:5000/ring"
SERVER_URL = "http://192.168.1.100:5000/ring"

# Налаштовуємо кнопковий піні GPIO16
button = Pin(16, Pin.IN, Pin.PULL_UP)


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Підключаємося до Wi-Fi...", end="")
        wlan.connect(WIFI_SSID, WIFI_PASS)
        while not wlan.isconnected():
            time.sleep(0.5)
            print(".", end="")
    print("\nWi-Fi підключено!")
    print("IP-адреса ESP32:", wlan.ifconfig()[0])


# Підключаємося до мережі при запуску
connect_wifi()
print("🔔 Звонок готовий і чекає на гостей!")

while True:
    if button.value() == 0:  # Замикання IO16 на GND
        print("🔔 Кнопку натиснуто! Надсилаємо сигнал...")

        try:
            # Відправляємо HTTP GET-запит
            response = urequests.get(SERVER_URL)
            print("Відповідь сервера код:", response.status_code)
            response.close()
        except Exception as e:
            print("Помилка відправки:", e)

        # Пауза 3 секунди, щоб уникнути декількох запитів при довгому утриманні
        time.sleep(3)

    time.sleep(0.05)