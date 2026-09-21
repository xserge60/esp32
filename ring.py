import time
import network
import urequests
import esp32
import machine
from machine import Pin, wake_reason, WDT, RTC, ADC
import json

__version__ = "1.0.48"

# Загружаем настройки из JSON-файла
try:
    with open("ring2bot.json", "r") as f:
        config = json.load(f)
except OSError:
    print("❌ Ошибка: файл ring2bot.json не найден!")
    config = {}

# Список сетей из JSON (или пустой список, если ключа нет)
WIFI_NETWORKS = config.get("wifi_networks", [])
BOT_TOKEN     = config.get("bot_token", "")
CHAT_ID       = config.get("chat_id", "")

PIN_BUTTON    = config.get("pin_button", 33)  # Кнопка на IO33
PIN_BUZZER    = config.get("pin_buzzer", 25)  # Зуммер на IO25
PIN_VOLTAGE   = config.get("pin_voltage", 35)  # Датчик напряжения на IO35

print("Звонок для калитки с низким энергопотреблением. Версия:", __version__)
print("Кнопка на пине", PIN_BUTTON, "зуммер на пине", PIN_BUZZER, "датчик напряжения на пине", PIN_VOLTAGE)

# === ЗАЩИТА ДЛЯ РАЗРАБОТКИ (ПАУЗА 5 СЕК) ===
# Если плата проснулась от сброса (RESET / включение питания / переподключение USB),
# даем 5 секунд на подсоединение по COM-порту до ухода в сон.
if machine.reset_cause() == machine.PWRON_RESET or machine.reset_cause() == machine.HARD_RESET:
    print("⏳ Ожидание 5 сек для загрузки/отладки...")
    time.sleep(5)

# Настройка АЦП на пине GPIO34
adc = ADC(PIN_VOLTAGE)
# Устанавливаем аттенюацию 11dB (диапазон измерений до ~3.3V)
adc.atten(ADC.ATTN_11DB)
# Ширина разрешения 12 бит (0..4095)
adc.width(ADC.WIDTH_12BIT)

def get_battery_voltage():
    uv_sum = 0
    for _ in range(10):
        uv_sum += adc.read_uv()
        time.sleep_ms(2)
    
    # 1. Напряжение на пине в Вольтах
    v_pin = (uv_sum / 10) / 1_000_000.0
    
    # 2. Умножаем на 2.0 (делитель 100k / 100k)
    v_bat = v_pin * 2.0 / 6.37 * 3.5
    
    return round(v_bat, 2)

def get_battery_voltage_safe():
    try:
        # Если резисторы припаяны — берем реальное значение
        voltage = get_battery_voltage()
        if voltage is not None and (type(voltage) is int or type(voltage) is float):
            return voltage

        print(f"🔋 Напряжение батареи: {voltage} В.")
        return 1.0  # Возвращаем 1.0 В, если значение некорректное
    except Exception as e:
        print(f"⚠️ Ошибка считывания АЦП: {e}")
        return 0.0  # Возвращаем 0, если возникла ошибка

# === РАБОТА С RTC-ПАМЯТЬЮ ДЛЯ ФЛАГА НЕОТПРАВЛЕННОГО ВЫЗОВА ===
rtc = RTC()

def get_pending_flag():
    """Проверяем, остался ли неотправленный вызов"""
    return rtc.memory() == b'1'

def set_pending_flag(status: bool):
    """Сохраняем состояние флага в RTC-памяти"""
    rtc.memory(b'1' if status else b'0')

# === ИНИЦИАЛИЗА ПИНОВ ===
button = Pin(PIN_BUTTON, Pin.IN, Pin.PULL_UP)
buzzer = Pin(PIN_BUZZER, Pin.OUT)
buzzer.value(0)

def sound_feedback(long=0.15):
    """Звуковой сигнал для гостя"""
    print("🔊 Подаем звуковой сигнал гостю...")
    buzzer.value(1)
    time.sleep(long)
    buzzer.value(0)

def connect_wifi():
    """Сканирует эфир и подключается к первой доступной сети из JSON"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        return True

    print("🔍 Сканирование Wi-Fi эфира...")
    try:
        scanned_nets = wlan.scan()
        # Извлекаем SSID из результатов сканирования (декодируем из bytes в str)
        available_ssids = [net[0].decode('utf-8') for net in scanned_nets]
        print("Найдено сетей в эфире:", available_ssids)
    except Exception as e:
        print("⚠️ Ошибка сканирования эфира:", e)
        available_ssids = []

    # Ищем пересечение доступных сетей со списком из JSON
    target_ssid = None
    target_pass = None

    for net in WIFI_NETWORKS:
        if net.get("ssid") in available_ssids:
            target_ssid = net.get("ssid")
            target_pass = net.get("pass")
            print(f"🎯 Найдена знакомая сеть: {target_ssid}")
            break

    # Если ни одна сеть из сканирования не совпала (или скрытый SSID),
    # берем самую первую сеть из JSON как fallback
    if not target_ssid and WIFI_NETWORKS:
        target_ssid = WIFI_NETWORKS[0].get("ssid")
        target_pass = WIFI_NETWORKS[0].get("pass")
        print(f"⚠️ Знакомых сетей в эфире не найдено. Пробуем первую из списка: {target_ssid}")

    if not target_ssid:
        print("❌ Ошибка: В ring2bot.json не задано ни одной Wi-Fi сети!")
        return False

    print(f"Подключение к {target_ssid}...", end="")
    wlan.connect(target_ssid, target_pass)
    
    timeout = 10
    while not wlan.isconnected() and timeout > 0:
        time.sleep(0.5)
        timeout -= 0.5
        print(".", end="")

    if wlan.isconnected():
        print("\n✅ Wi-Fi подключен! IP:", wlan.ifconfig()[0])
        time.sleep(0.2)
        return True

    print("\n❌ Wi-Fi не подключен!")
    return False

def send_telegram(text, retries=2):
    encoded_text = text.replace(" ", "%20").replace("\n", "%0A")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={encoded_text}"

    for attempt in range(1, retries + 1):
        try:
            response = urequests.get(url, timeout=8)
            success = response.status_code == 200
            response.close()
            if success:
                return True
            print(f"⚠️ Telegram вернул код {response.status_code} (попытка {attempt})")
        except Exception as e:
            print(f"⚠️ Ошибка запроса к Telegram (попытка {attempt}):", e)

        if attempt < retries:
            time.sleep(1)

    return False

# === ОСНОВНОЙ СЦЕНАРИЙ ===

is_button_press = (wake_reason() == machine.PIN_WAKE or wake_reason() == 2)

# 1. Если физически нажата кнопка — взводим флаг
if is_button_press:
    print("🔔 Кнопка нажата! Проснулись из Deep Sleep...")
    sound_feedback(0.15)
    set_pending_flag(True)

# 2. Проверяем наличие неотправленного вызова
if get_pending_flag():
    print("📩 Есть неотправленное сообщение! Начинаем обработку...")

    # Аппаратный Watchdog на 25 секунд
    wdt = WDT(timeout=25000)

    if connect_wifi():
        if send_telegram(f"Звонят в калитку!\n🔋 Напряжение батареи: {get_battery_voltage_safe()} В."):
            print(f"✅ Уведомление доставлено! Тип при чтении {type(adc.read())}")
            set_pending_flag(False)
            sound_feedback(0.5)
        else:
            print("⚠️ Не удалось отправить сообщение в Telegram.")
    else:
        print("⚠️ Не удалось подключиться к Wi-Fi.")

    # 3. Если сбой — засыпаем на 10 секунд для повторной попытки
    if get_pending_flag():
        print("⏳ Ошибка доставки. Засыпаем на 10 сек для повторной попытки...")
        btn_pin = Pin(PIN_BUTTON, Pin.IN, Pin.PULL_UP)
        esp32.wake_on_ext0(pin=btn_pin, level=esp32.WAKEUP_ALL_LOW)
        machine.deepsleep(10000)

# === ЕСЛИ ВСЕ УСПЕШНО — УХОДИМ В ОБЫЧНЫЙ СОН ДО КНОПКИ ===
btn_pin = Pin(PIN_BUTTON, Pin.IN, Pin.PULL_UP)
esp32.wake_on_ext0(pin=btn_pin, level=esp32.WAKEUP_ALL_LOW)

print("💤 Все сообщения доставлены. Уходим в Deep Sleep до следующего звонка...")
time.sleep(0.1)
machine.deepsleep()