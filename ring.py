import time
import network
import urequests
import esp32
import machine
from machine import Pin, wake_reason

import json

__version__ = "1.0.10"

# Загружаем настройки из JSON-файла
try:
    with open("ring2bot.json", "r") as f:
        config = json.load(f)
except OSError:
    print("❌ Ошибка: файл ring2bot.json не найден!")
    config = {}

print("Звонок для калитки с низким энергопотреблением. Версия:", __version__)

# === ЗАЩИТА ДЛЯ РАЗРАБОТКИ ===
# Если плата проснулась от сброса (RESET / включение питания),
# даем 5 секунд на подсоединение по COM-порту до ухода в сон.
if machine.reset_cause() == machine.PWRON_RESET or machine.reset_cause() == machine.HARD_RESET:
    print("⏳ Ожидание 5 сек для загрузки/отладки...")
    time.sleep(5)

# Достаем переменные
WIFI_SSID = config.get("wifi_ssid", "")
WIFI_PASS = config.get("wifi_pass", "")
BOT_TOKEN = config.get("bot_token", "")
CHAT_ID = config.get("chat_id", "")

# === ИНИЦИАЛИЗА ПИНОВ ===
# Пин кнопки (GPIO33 - RTC пин) и пин зуммера (GPIO17)
BUTTON_PIN = 33
BUZZER_PIN = 17

buzzer = Pin(BUZZER_PIN, Pin.OUT)
buzzer.value(0)


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASS)
        # Ждем подключения максимум 10 секунд (чтобы не сажать батарею при сбоях сети)
        timeout = 10
        while not wlan.isconnected() and timeout > 0:
            time.sleep(0.5)
            timeout -= 0.5
    return wlan.isconnected()


def send_telegram(text):
    encoded_text = text.replace(" ", "%20")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={encoded_text}"
    try:
        response = urequests.get(url)
        success = response.status_code == 200
        response.close()
        return success
    except:
        return False


def sound_feedback():
    buzzer.value(1)
    time.sleep(0.15)
    buzzer.value(0)
    time.sleep(0.1)
    buzzer.value(1)
    time.sleep(0.15)
    buzzer.value(0)


# === ОСНОВНОЙ СЦЕНАРИЙ ПРИ ПРОСЫПАНИИ ===

# Проверяем, почему проснулась плата
# machine.PIN_WAKE (код 2) означает, что проснулись от нажатия кнопки
if wake_reason() == machine.PIN_WAKE or wake_reason() == 2:
    print("🔔 Кнопка нажата! Проснулись из Deep Sleep...")

    if connect_wifi():
        if send_telegram("Звонят в калитку!"):
            sound_feedback()

# === НАСТРОЙКА УСЛОВИЯ СЛЕДУЮЩЕГО ПРОБУЖДЕНИЯ И УХОД В СОН ===

btn_pin = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)

esp32.wake_on_ext0(pin=btn_pin, level=esp32.WAKEUP_ALL_LOW)

print("💤 Уходим в Deep Sleep до следующего звонка...")
time.sleep(0.1)  # Даем системным процессам завершиться

# Отключаем плату (уходим в глубокий сон)
machine.deepsleep()
