import time
import network
import urequests
import esp32
import machine
from machine import Pin, wake_reason, WDT

import json

__version__ = "1.0.22"

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

PIN_BUTTON = config.get("pin_button", 33)  # Кнопка звонка со сбросом ESP32
PIN_BUZZER = config.get("pin_buzzer", 25)  # Зуммер на IO25

print("Звонок для калитки с низким энергопотреблением. Версия:", __version__)
print("Кнопка на пине", PIN_BUTTON, "зуммер на пине", PIN_BUZZER)

# === ЗАЩИТА ДЛЯ РАЗРАБОТКИ ===
# Если плата проснулась от сброса (RESET / включение питания),
# даем 5 секунд на подсоединение по COM-порту до ухода в сон.
if machine.reset_cause() == machine.PWRON_RESET or machine.reset_cause() == machine.HARD_RESET:
    print("⏳ Ожидание 5 сек для загрузки/отладки...")
    time.sleep(5)

# === ИНИЦИАЛИЗА ПИНОВ ===
button = Pin(PIN_BUTTON, Pin.IN, Pin.PULL_UP) # Кнопка звонка на IO33
buzzer = Pin(PIN_BUZZER, Pin.OUT)             # Зуммер на IO25

# Включаем/выключаем пищалку при старте, чтобы она точно молчала
buzzer.value(0)


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if not wlan.isconnected():
        print("Подключение к Wi-Fi...", end="")
        wlan.connect(WIFI_SSID, WIFI_PASS)
        # Ждем подключения максимум 10 секунд (чтобы не сажать батарею при сбоях сети)
        timeout = 10
        while not wlan.isconnected() and timeout > 0:
            time.sleep(0.5)
            timeout -= 0.5
            print(".", end="")

    if wlan.isconnected():
        print("\n✅ Wi-Fi подключен! IP:", wlan.ifconfig()[0])
        time.sleep(0.3)  # даём DNS/стеку время устаканиться после подключения
        return True

    print("\n❌ Wi-Fi не подключен!")
    return False

def send_telegram(text, retries=2):
    encoded_text = text.replace(" ", "%20")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={encoded_text}"

    for attempt in range(1, retries + 1):
        try:
            response = urequests.get(url)
            success = response.status_code == 200
            response.close()
            if success:
                return True
            print(f"⚠️ Telegram вернул код {response.status_code} (попытка {attempt})")
        except Exception as e:
            print(f"⚠️ Ошибка запроса к Telegram (попытка {attempt}):", e)

        if attempt < retries:
            time.sleep(1)  # небольшая пауза перед повтором

    return False

def sound_feedback(long=0.5):
    """сигнал зуммера для подтверждения действия"""
    print("🔊 Подаем звуковой сигнал гостю...")
    buzzer.value(1)       # Включаем пищалку
    time.sleep(long)      # Пищим 150 мс
    buzzer.value(0)


# === ОСНОВНОЙ СЦЕНАРИЙ ПРИ ПРОСЫПАНИИ ===

# Проверяем, почему проснулась плата
# machine.PIN_WAKE (код 2) означает, что проснулись от нажатия кнопки
if wake_reason() == machine.PIN_WAKE or wake_reason() == 2:
    print("🔔 Кнопка нажата! Проснулись из Deep Sleep...")
    # подтвеждаем гостю, что кнопка нажата хорошо
    sound_feedback(0.15)

    # Watchdog: если весь процесс (Wi-Fi + отправка) не уложится в 25 сек — жёсткий сброс
    wdt = WDT(timeout=25000)

    if connect_wifi():
        if send_telegram("Звонят в калитку!"):
            sound_feedback(0.5)

# === НАСТРОЙКА УСЛОВИЯ СЛЕДУЮЩЕГО ПРОБУЖДЕНИЯ И УХОД В СОН ===

btn_pin = Pin(PIN_BUTTON, Pin.IN, Pin.PULL_UP)

esp32.wake_on_ext0(pin=btn_pin, level=esp32.WAKEUP_ALL_LOW)

print("💤 Уходим в Deep Sleep до следующего звонка...")
time.sleep(0.1)  # Даем системным процессам завершиться

# Отключаем плату (уходим в глубокий сон)
machine.deepsleep()
