import time
import network
import urequests
from machine import Pin

import json

__version__ = "1.0.21"

# Загружаем настройки из JSON-файла
try:
    with open("ring2bot.json", "r") as f:
        config = json.load(f)
except OSError:
    print("❌ Ошибка: файл ring2bot.json не найден!")
    config = {}

# Достаем переменные
WIFI_SSID = config.get("wifi_ssid", "")
WIFI_PASS = config.get("wifi_pass", "")
BOT_TOKEN = config.get("bot_token", "")
CHAT_ID   = config.get("chat_id", "")

PIN_BUTTON0 = config.get("pin_button0", 33)  # Кнопка звонка со сбросом ESP32
PIN_BUTTON1 = config.get("pin_button1", 26)  # Кнопка звонка на IO26
PIN_BUZZER = config.get("pin_buzzer", 25)  # Зуммер на IO25

# === ИНИЦИАЛИЗА ПИНОВ ===
button0 = Pin(PIN_BUTTON0, Pin.IN, Pin.PULL_UP) # Кнопка звонка на IO33
button1 = Pin(PIN_BUTTON1, Pin.IN, Pin.PULL_UP) # Кнопка звонка на IO26
buzzer = Pin(PIN_BUZZER, Pin.OUT)             # Зуммер на IO25

# Включаем/выключаем пищалку при старте, чтобы она точно молчала
buzzer.value(0)

print("Звонок для калитки. Версия:", __version__)
print("Кнопка на пине", PIN_BUTTON0, "или на пине", PIN_BUTTON1, "зуммер на пине", PIN_BUZZER)

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Подключение к Wi-Fi...", end="")
        wlan.connect(WIFI_SSID, WIFI_PASS)
        while not wlan.isconnected():
            time.sleep(0.5)
            print(".", end="")
    print("\n✅ Wi-Fi подключен! IP:", wlan.ifconfig()[0])


def sound_feedback():
    """Короткий двойной или один длинный сигнал об успешной доставке"""
    print("🔊 Подаем звуковой сигнал гостю...")
    buzzer.value(1)       # Включаем пищалку
    time.sleep(0.5)      # Пищим 150 мс
    # buzzer.value(0)
    # time.sleep(0.1)
    # buzzer.value(1)       # Второй короткий "пик"
    # time.sleep(0.15)
    buzzer.value(0)       # Выключаем


def send_telegram(text):
    encoded_text = text.replace(" ", "%20")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={encoded_text}"

    try:
        response = urequests.get(url)
        
        # Проверяем, что Telegram реально принял сообщение (Код 200)
        if response.status_code == 200:
            print("📩 Сообщение успешно доставлено!")
            response.close()
            return True  # Возвращаем УСПЕХ
        else:
            print(f"⚠️ Ошибка Telegram API: {response.status_code}")
            response.close()
            return False
            
    except Exception as e:
        print("❌ Ошибка отправки:", e)
        return False


# Подключаемся к сети
connect_wifi()
print("🔔 Звонок готов к работе!")

while True:
    if button0.value() == 0 or button1.value() == 0:  # Замыкание кнопки
        print("🔔 Кнопка нажата! Отправляем уведомление...")

        # Пытаемся отправить сообщение
        success = send_telegram("Кто-то звонит в калитку!")

        if success:
            # Даем звуковой сигнал гостю ТОЛЬКО при успешной отправке!
            sound_feedback()
        else:
            print("❌ Сигнал гостю не подаем, так как сообщение не ушло.")

        # Задержка 5 секунд от повторных нажатий
        time.sleep(5)

    time.sleep(0.05)