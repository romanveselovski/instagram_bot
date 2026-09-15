import time
import random
from pathlib import Path

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service

try:
    # webdriver_manager может не совпасть по версии с локальным Chrome.
    # Selenium Manager (встроенный) обычно надежнее, но оставим fallback.
    from webdriver_manager.chrome import ChromeDriverManager  # type: ignore

    _HAS_WDM = True
except Exception:
    _HAS_WDM = False

# ================= НАСТРОЙКИ (ИЗМЕНИТЕ ЗДЕСЬ) =================
# ВАЖНО: логин/пароль больше не храним в коде — авторизация выполняется вручную в браузере.
MESSAGE = "Ciao, rappresentiamo Eden — un marchio di caviale nero premium con consegna in tutto il mondo. Sareste aperti a ricevere dei campioni?"
# За один запуск обрабатываем только первые N строк из profile_links.csv, пишем лог и удаляем их из файла.
BATCH_SIZE = 20
PROFILE_LINKS_CSV = "profile_links.csv"
PROFILE_LINKS_UPDATED_CSV = "profile_links_updated.csv"
# Следующая ссылка открывается только после полного завершения предыдущей (никакого параллелизма).
PAUSE_BETWEEN_CLIENTS_SEC_MIN = 20
PAUSE_BETWEEN_CLIENTS_SEC_MAX = 40
PAUSE_BEFORE_NEXT_PROFILE_SEC = 2  # короткая пауза перед открытием следующего URL
MESSAGE_BUTTON_TIMEOUT_SEC = 5  # не ждём долго, если кнопки сообщения нет
STATUS_SUCCESS = "Успешно отправлено"
# ============================================================

# Создаем настройки для браузера, чтобы он был менее заметен для антибот-систем
options = webdriver.ChromeOptions()
options.add_argument("--disable-blink-features=AutomationControlled") # Скрываем признак автоматизации
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option('useAutomationExtension', False)

# Инициализируем драйвер
driver = None

try:
    # Selenium Manager сам подберет подходящий chromedriver под установленный Chrome.
    driver = webdriver.Chrome(options=options)
except Exception:
    if not _HAS_WDM:
        raise
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

# Выполняем скрипт, чтобы скрыть свойство navigator.webdriver
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

wait = WebDriverWait(driver, 20) # Ожидание до 20 секунд для появления элементов на странице


def _first_present(selectors, timeout=30):
    """
    Возвращает первый найденный элемент по списку селекторов.
    selectors: list[tuple[By, str]]
    """
    local_wait = WebDriverWait(driver, timeout)

    def _probe(_driver):
        for by, value in selectors:
            els = _driver.find_elements(by, value)
            if els:
                return els[0]
        return False

    return local_wait.until(_probe)


def _read_profile_links_df() -> pd.DataFrame:
    """Читает profile_links.csv (разделитель ; или старый формат с запятой)."""
    path = Path(PROFILE_LINKS_CSV)
    with path.open(encoding="utf-8") as f:
        first = f.readline()
    sep = ";" if ";" in first else ","
    return pd.read_csv(path, sep=sep, encoding="utf-8")


def _is_legacy_profile_format(df: pd.DataFrame) -> bool:
    return "instagram" not in df.columns and "Profile Links" in df.columns


def _append_results_log(rows: list[dict]) -> None:
    """Дописывает (или создаёт) profile_links_updated.csv с тем же разделителем ;."""
    if not rows:
        return
    path = Path(PROFILE_LINKS_UPDATED_CSV)
    new_df = pd.DataFrame(rows)
    if path.exists() and path.stat().st_size > 0:
        try:
            old_df = pd.read_csv(path, sep=";", encoding="utf-8")
        except Exception:
            old_df = pd.read_csv(path, encoding="utf-8")
        out = pd.concat([old_df, new_df], ignore_index=True)
    else:
        out = new_df
    out.to_csv(path, sep=";", index=False, encoding="utf-8")


def _save_profile_links_remaining(df: pd.DataFrame) -> None:
    """Перезаписывает profile_links.csv оставшимися строками (заголовок сохраняется)."""
    Path(PROFILE_LINKS_CSV).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROFILE_LINKS_CSV, sep=";", index=False, encoding="utf-8")


def instagram_login():
    """Открывает страницу логина и ждёт ручной авторизации пользователя."""
    print("\n" + "=" * 60)
    print("ПАУЗА: скрипт запущен, рассылка ещё НЕ началась.")
    print("Откройте браузер, войдите в Instagram (логин, пароль, капча, 2FA).")
    print("Когда вход выполнен — вернитесь в этот терминал и нажмите Enter,")
    print("чтобы разрешить продолжение выполнения.")
    print("=" * 60 + "\n")
    driver.get("https://www.instagram.com/accounts/login/")
    time.sleep(2)

    input(">>> Нажмите Enter, когда авторизовались и можно продолжать... ")

    # Проверяем, что мы больше не на странице логина (или хотя бы есть куки сессии)
    if "/accounts/login" in driver.current_url:
        # Иногда URL не меняется сразу — дадим еще немного времени
        try:
            WebDriverWait(driver, 15).until(lambda d: "/accounts/login" not in d.current_url)
        except Exception:
            try:
                driver.save_screenshot("login_error.png")
            except Exception:
                pass
            print("Похоже, вы всё ещё на странице логина. Завершаю работу. (Скрин: login_error.png)")
            driver.quit()
            exit()

    print("Авторизация подтверждена, продолжаем.")

def send_dm_to_profile(profile_url, message_text):
    """Функция для отправки сообщения одному профилю"""
    try:
        print(f"\n--- Обработка: {profile_url} ---")
        driver.get(profile_url)
        time.sleep(4) # Ждем загрузки профиля

        # Ищем и нажимаем кнопку сообщения
        # В разных версиях UI она может называться: "Сообщение" / "Отправить сообщение" / "Message" / "Send message"
        try:
            message_button = _first_present(
                [
                    (By.XPATH, "//*[@role='button' and normalize-space(.)='Сообщение']"),
                    (By.XPATH, "//*[@role='button' and normalize-space(.)='Отправить сообщение']"),
                    (By.XPATH, "//*[@role='button' and normalize-space(.)='Message']"),
                    (By.XPATH, "//*[@role='button' and normalize-space(.)='Send message']"),
                    # fallback: div-кнопки
                    (By.XPATH, "//div[normalize-space(.)='Сообщение']"),
                    (By.XPATH, "//div[normalize-space(.)='Отправить сообщение']"),
                    (By.XPATH, "//div[normalize-space(.)='Message']"),
                    (By.XPATH, "//div[normalize-space(.)='Send message']"),
                ],
                timeout=MESSAGE_BUTTON_TIMEOUT_SEC,
            )
        except TimeoutException:
            print(
                f"Не удалось найти кнопку сообщения для {profile_url}. Возможно, профиль закрыт или вы заблокированы."
            )
            return "Кнопка сообщения не найдена"

        try:
            message_button.click()
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", message_button)
            except Exception as click_err:
                print(
                    f"Не удалось нажать кнопку сообщения для {profile_url}: {click_err}"
                )
                return "Не удалось нажать кнопку сообщения"
        print("Кнопка сообщения нажата.")
        time.sleep(3)

        # Находим поле для ввода сообщения
        # В Instagram это может быть <textarea> или contenteditable (div role="textbox" с вложенным <p>).
        message_input = _first_present(
            [
                # Твой конкретный инпут (Lexical editor внутри DM)
                (By.CSS_SELECTOR, "div[contenteditable='true'][role='textbox'][data-lexical-editor='true']"),
                (By.CSS_SELECTOR, "div[contenteditable='true'][role='textbox'][aria-placeholder*='Напишите сообщение']"),
                # fallback-варианты
                (By.TAG_NAME, "textarea"),
                (By.CSS_SELECTOR, "div[role='textbox'][contenteditable='true']"),
                (By.CSS_SELECTOR, "[contenteditable='true'][role='textbox']"),
                # самый слабый fallback: p-блок внутри поля ввода
                (By.CSS_SELECTOR, "p.xat24cr.xdj266r[dir='auto']"),
                (By.CSS_SELECTOR, "p[dir='auto']"),
            ],
            timeout=20,
        )

        # Фокусируемся в поле ввода
        try:
            message_input.click()
        except Exception:
            driver.execute_script("arguments[0].focus();", message_input)

        # Если попали в <p>, лучше подняться до родителя contenteditable/role="textbox"
        try:
            if (message_input.tag_name or "").lower() == "p":
                # 1) самый правильный контейнер: role=textbox + contenteditable
                try:
                    parent = message_input.find_element(
                        By.XPATH, "./ancestor::*[@role='textbox' and @contenteditable='true'][1]"
                    )
                    message_input = parent
                except Exception:
                    # 2) просто ближайший contenteditable
                    parent = message_input.find_element(By.XPATH, "./ancestor::*[@contenteditable='true'][1]")
                    message_input = parent
        except Exception:
            pass

        # Очищаем поле (на всякий случай)
        try:
            message_input.clear()  # textarea
        except Exception:
            # contenteditable
            try:
                message_input.send_keys(Keys.CONTROL, "a")
                message_input.send_keys(Keys.BACKSPACE)
            except Exception:
                pass

        # Вводим текст с небольшой задержкой (имитация человека)
        for character in message_text:
            message_input.send_keys(character)
            time.sleep(random.uniform(0.05, 0.15))
        
        print("Сообщение введено.")
        time.sleep(1)

        # Отправляем сообщение (Enter)
        message_input.send_keys(Keys.ENTER)
        print("Сообщение отправлено!")

        # Небольшая пауза перед отправкой следующего
        time.sleep(5)
        return STATUS_SUCCESS

    except Exception as e:
        print(f"Произошла ошибка при отправке для {profile_url}: {e}")
        return f"Ошибка: {str(e)[:50]}" # Возвращаем первые 50 символов ошибки

def main():
    """Главная функция"""
    print("Скрипт запущен. Сначала будет пауза на ручной вход в Instagram.")
    # 1. Читаем список из CSV
    try:
        df = _read_profile_links_df()
    except FileNotFoundError:
        print(f"Ошибка: файл '{PROFILE_LINKS_CSV}' не найден в папке с программой.")
        driver.quit()
        return
    except Exception as e:
        print(f"Ошибка при чтении CSV: {e}")
        driver.quit()
        return

    if df.empty:
        print(f"Файл '{PROFILE_LINKS_CSV}' пуст — нечего отправлять.")
        driver.quit()
        return

    legacy = _is_legacy_profile_format(df)
    n = min(BATCH_SIZE, len(df))
    batch = df.iloc[:n].copy()
    remainder = df.iloc[n:].copy()

    print(
        f"В очереди строк: {len(df)}. За этот запуск обработаем первых {n} "
        f"(остальные {len(remainder)} останутся в '{PROFILE_LINKS_CSV}')."
    )

    # 2. Авторизуемся (Instagram уже открывается внутри instagram_login)
    instagram_login()

    results: list[dict] = []

    # Строго по очереди: одна ссылка → полный цикл отправки → только потом следующая.
    prev_status: str | None = None
    for pos in range(len(batch)):
        if pos > 0 and prev_status == STATUS_SUCCESS:
            print(
                f"\nПредыдущая ссылка обработана. Пауза {PAUSE_BEFORE_NEXT_PROFILE_SEC} с перед следующей..."
            )
            time.sleep(PAUSE_BEFORE_NEXT_PROFILE_SEC)
        elif pos > 0:
            print("\nПредыдущая ссылка без успешной отправки — сразу к следующей.")

        row = batch.iloc[pos]
        if legacy:
            link = str(row["Profile Links"]).strip()
            row_dict: dict = {"Profile Links": link}
        else:
            link = str(row["instagram"]).strip()
            row_dict = {k: row[k] for k in row.index}
            row_dict["instagram"] = link

        print(
            f"\n>>> Очередь {pos + 1} из {len(batch)} (в файле было строк: {len(df)}). Сейчас: {link}"
        )
        status = send_dm_to_profile(link, MESSAGE)
        prev_status = status
        row_dict["status"] = status
        results.append(row_dict)
        print(f"    Статус по этой ссылке: {status}")

        if pos < len(batch) - 1:
            if status == STATUS_SUCCESS:
                sleep_time = random.randint(
                    PAUSE_BETWEEN_CLIENTS_SEC_MIN, PAUSE_BETWEEN_CLIENTS_SEC_MAX
                )
                print(f"Ждем {sleep_time} с перед следующим клиентом (по очереди)...")
                time.sleep(sleep_time)
            else:
                print("Паузу между клиентами пропускаем — переходим к следующей ссылке.")

    _append_results_log(results)
    _save_profile_links_remaining(remainder)

    print(
        f"\nГотово. Лог записан в '{PROFILE_LINKS_UPDATED_CSV}' "
        f"(добавлено строк: {len(results)}). "
        f"Из '{PROFILE_LINKS_CSV}' удалены обработанные строки; осталось: {len(remainder)}."
    )

    driver.quit()

if __name__ == "__main__":
    main()