"""Телеграм бот."""
import email
import imaplib
import logging
import os
import threading
import time
from datetime import datetime
from email.header import decode_header

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telebot import TeleBot, types

load_dotenv()
logging.basicConfig(
    filename='main.log',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,
)

MY_TELEGRAM_ID = int(os.getenv('MY_TELEGRAM_ID'))
INTERVAL = int(os.getenv('INTERVAL'))
SLEEP = int(os.getenv('SLEEP'))
MAIL_PASS = os.getenv('MAIL_PASS')
MAIL_USER = os.getenv('MAIL_USER')
MAIL_SERVICE = os.getenv('MAIL_SERVICE')

bot = TeleBot(os.getenv('BOT_TOKEN'))
seen_uid_list = []


def imap_connect():
    """Создает новое соединение с IMAP-сервером и выбирает INBOX."""
    logging.debug('Попытка соединение с IMAP-сервером.')
    imap = imaplib.IMAP4_SSL(MAIL_SERVICE)
    imap.login(MAIL_USER, MAIL_PASS)
    imap.select('INBOX')
    logging.debug('Успешное соединение с IMAP-сервером.')
    return imap


def is_valid_id(chat_id):
    """Проверка права доступа."""
    if chat_id != MY_TELEGRAM_ID:
        logging.debug(
            f'Ошибка доступа, юзер {chat_id} пытался восбользовться ботом.'
        )
        send_message(chat_id, f'Твой id - {chat_id}. У тебя нет доступа!')
        return False
    return True


def send_message(chat_id, message, reply_markup=None):
    """Отправка сообщений в Телеграм."""
    logging.debug('Попытка отправить сообщение в ТГ')
    try:
        bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=reply_markup
        )
        logging.debug('Сообщение отправлено в ТГ')
    except Exception as error:
        logging.error(
            f'Сбой при отправке сообщения в ТГ: {error}',
            exc_info=True
        )


def get_uid_list(imap):
    """Получает список UID всех непрочитанных писем."""
    logging.debug('Попытка получить список UID')
    response = imap.uid('search', 'UNSEEN', 'ALL')
    if response[0] == 'OK':
        return response[1][0].decode().split()
    return []


def convert_text(msg):
    """Конвертируем тело сообщения."""
    logging.debug('Попытка конвертировать тело сообщения.')
    for part in msg.walk():
        content_type = part.get_content_type()
        if content_type == 'text/plain' or content_type == 'text/html':
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or 'utf-8'
            if payload:
                text = payload.decode(charset, errors='ignore')
                soup = BeautifulSoup(text, 'lxml')
                clean_text = soup.get_text(separator='\n', strip=True)
    logging.debug('Сообщение сконвертировано.')
    return clean_text


def read_email_message(uid, imap, header_only=False):
    """Чтение письма."""
    logging.debug('Попытка чтения письма.')
    fetch_mode = '(RFC822)'
    if header_only:
        fetch_mode = '(BODY.PEEK[HEADER])'
    res, msg = imap.uid('fetch', uid, fetch_mode)
    if res != 'OK':
        return f'Не смог прочитать сообщение {uid}'
    msg = email.message_from_bytes(msg[0][1])
    raw_from = msg['From']
    decoded_from, encoding = decode_header(raw_from)[0]
    if isinstance(decoded_from, bytes):
        decoded_from = decoded_from.decode(encoding or 'utf-8')
    sender_name, sender_email = email.utils.parseaddr(decoded_from)
    letter_from = (
        f'{sender_name} <{sender_email}>'
        if sender_name else sender_email
    )
    letter_title, encoding = decode_header(msg['Subject'])[0]
    if isinstance(letter_title, bytes):
        letter_title = letter_title.decode(encoding or 'utf-8')
    message = f'📧 Тема письма: {letter_title} \n'
    message += f'👤 Отправитель: {letter_from} \n'
    if not header_only:
        letter_date_tuple = email.utils.parsedate_tz(msg['Date'])
        if letter_date_tuple:
            dt = datetime(*letter_date_tuple[:6])
            letter_date = dt.strftime('%d.%m.%Y %H:%M')
        else:
            letter_date = 'Неизвестная дата'
        letter_text = convert_text(msg)
        message += f'📅 Дата отправки: {letter_date} \n'
        message += f'📝 Текст письма:\n {letter_text}'
    logging.debug('Письмо прочитано.')
    return message


@bot.message_handler(commands=['start'])
def wake_up(message):
    """Запуск бота и создание кнопки."""
    chat_id = message.chat.id
    name = message.chat.first_name
    if is_valid_id(chat_id):
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        button_check = types.KeyboardButton('/check')
        keyboard.add(button_check)
        send_message(MY_TELEGRAM_ID, f'Привет, {name}.', keyboard)


@bot.message_handler(commands=['check'])
def check(message):
    """Ручная проверка почты."""
    global seen_uid_list
    chat_id = message.chat.id
    if is_valid_id(chat_id):
        try:
            send_message(MY_TELEGRAM_ID, 'Читаю почту...')
            imap = imap_connect()
            seen_uid_list = get_uid_list(imap)
            if len(seen_uid_list) == 0:
                send_message(MY_TELEGRAM_ID, 'У вас нет новых сообщений.')
            send_message(
                MY_TELEGRAM_ID,
                f'У тебя {len(seen_uid_list)} непрочитанных сообщений.'
            )
            for uid in seen_uid_list:
                message = read_email_message(uid, imap, True)
                keyboard = types.InlineKeyboardMarkup()
                btn_read = types.InlineKeyboardButton(
                    '📖 Прочитать',
                    callback_data=f'read_{uid}'
                )
                keyboard.add(btn_read)
                send_message(
                    MY_TELEGRAM_ID,
                    message,
                    keyboard
                )
        except Exception as error:
            logging.error(f'Ошибка в check: {error}', exc_info=True)
            send_message(
                MY_TELEGRAM_ID,
                f'Ошибка в check: {error}'
            )
        finally:
            imap.logout()


@bot.callback_query_handler(func=lambda call: call.data.startswith("read_"))
def read_letter(call):
    """Обработчик нажатия кнопки 'Прочитать'."""
    global seen_uid_list
    try:
        letter_id = call.data.split('_')[1]
        imap = imap_connect()
        seen_uid_list.remove(letter_id)
        letter = read_email_message(letter_id, imap)
        send_message(MY_TELEGRAM_ID, letter)
    except Exception as error:
        logging.error(f'Ошибка в read_letter: {error}', exc_info=True)
        send_message(
            MY_TELEGRAM_ID,
            f'Ошибка в read_letter: {error}'
        )
    finally:
        imap.logout()


def check_new_messages():
    """Автоматическая проверка почты."""
    global seen_uid_list
    while True:
        time.sleep(SLEEP)
        try:
            imap = imap_connect()
            new_uid_list = get_uid_list(imap)
            new_uid_list = list(set(new_uid_list) - set(seen_uid_list))
            if new_uid_list:
                send_message(
                    MY_TELEGRAM_ID,
                    f'📩 У вас {len(new_uid_list)} новых сообщений'
                )
                for uid in new_uid_list:
                    seen_uid_list.append(uid)
                    message = read_email_message(uid, imap, True)
                    keyboard = types.InlineKeyboardMarkup()
                    btn_read = types.InlineKeyboardButton(
                        '📖 Прочитать',
                        callback_data=f'read_{uid}'
                    )
                    keyboard.add(btn_read)
                    send_message(
                        MY_TELEGRAM_ID,
                        message,
                        keyboard
                    )
        except Exception as error:
            logging.error(
                f'Ошибка в check_new_messages: {error}',
                exc_info=True
            )
            send_message(
                MY_TELEGRAM_ID,
                f'Ошибка в check_new_messages: {error}'
            )
        finally:
            imap.logout()


threading.Thread(target=check_new_messages, daemon=True).start()
bot.polling(interval=INTERVAL)
