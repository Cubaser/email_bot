"""Телеграмм бот."""
import email
import imaplib
import os
from datetime import datetime
from email.header import decode_header

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telebot import TeleBot, types

load_dotenv()

MY_TELEGRAMM_ID = int(os.getenv('MY_TELEGRAMM_ID'))

mail_pass = os.getenv('MAIL_PASS')
username = os.getenv('MAIL_USER')
imap_server = os.getenv('MAIL_SERVICE')
bot = TeleBot(os.getenv('BOT_TOKEN'))


def imap_connect():
    """Создает новое соединение с IMAP-сервером и выбирает INBOX."""
    imap = imaplib.IMAP4_SSL(imap_server)
    imap.login(username, mail_pass)
    imap.select('INBOX')
    return imap


def get_uid_list(imap):
    """Получает список UID всех непрочитанных писем."""
    response = imap.uid('search', 'UNSEEN', 'ALL')
    if response[0] == 'OK':
        return response[1][0].decode().split()
    return []


def convert_text(msg):
    """Конвертируем тело сообщения."""
    for part in msg.walk():
        content_type = part.get_content_type()

        if content_type == 'text/plain' or content_type == 'text/html':
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or 'utf-8'

            if payload:
                text = payload.decode(charset, errors='ignore')
                soup = BeautifulSoup(text, 'lxml')
                clean_text = soup.get_text(separator='\n', strip=True)

    return clean_text


def read_headers_message(uid, imap):
    """Читает заголовки письма (тему и отправителя)."""
    res, msg = imap.uid('fetch', uid, '(BODY.PEEK[HEADER])')
    if res != 'OK':
        return f'Не смог прочитать сообщение {uid}'

    msg = email.message_from_bytes(msg[0][1])

    # Получаем имя и email отправителя
    raw_from = msg["From"]
    decoded_from, encoding = decode_header(raw_from)[0]
    # Если надо декодируем
    if isinstance(decoded_from, bytes):
        decoded_from = decoded_from.decode(encoding or 'utf-8')
    sender_name, sender_email = email.utils.parseaddr(decoded_from)
    # Если есть имя, то используем его, иначе просто email
    letter_from = (
        f'{sender_name} <{sender_email}>'
        if sender_name else sender_email
    )

    # Получаем тему письма
    letter_title, encoding = decode_header(msg['Subject'])[0]
    # Если надо декодируем
    if isinstance(letter_title, bytes):
        letter_title = letter_title.decode(encoding or 'utf-8')

    message = f'📧 Тема письма: {letter_title} \n'
    message += f'👤 Отправитель: {letter_from} \n'

    return message


def read_email_message(uid, imap):
    """Полное чтение письма."""
    res, msg = imap.uid('fetch', uid, '(RFC822)')
    if res != 'OK':
        return f'Не смог прочитать сообщение {uid}'

    msg = email.message_from_bytes(msg[0][1])

    # Получаем дату письма
    letter_date_tuple = email.utils.parsedate_tz(msg['Date'])
    if letter_date_tuple:
        # Конвертируем в datetime
        dt = datetime(*letter_date_tuple[:6])
        # Форматируем в нужный вид
        letter_date = dt.strftime('%d.%m.%Y %H:%M')
    else:
        letter_date = 'Неизвестная дата'

    # Получаем имя и email отправителя
    raw_from = msg['From']
    decoded_from, encoding = decode_header(raw_from)[0]
    # Если надо декодируем
    if isinstance(decoded_from, bytes):
        decoded_from = decoded_from.decode(encoding or 'utf-8')
    sender_name, sender_email = email.utils.parseaddr(decoded_from)
    # Если есть имя, то используем его, иначе просто email
    letter_from = (
        f'{sender_name} <{sender_email}>'
        if sender_name else sender_email
    )

    # Получаем тему письма
    letter_title, encoding = decode_header(msg['Subject'])[0]
    # Если надо декодируем
    if isinstance(letter_title, bytes):
        letter_title = letter_title.decode(encoding or 'utf-8')

    letter_text = convert_text(msg)

    message = f'📧 Тема письма: {letter_title} \n'
    message += f'👤 Отправитель: {letter_from} \n'
    message += f'📅 Дата отправки: {letter_date} \n'
    message += f'📝 Текст письма:\n {letter_text}'

    return message


@bot.message_handler(commands=['start'])
def wake_up(message):
    """Запуск бота и создание кнопки."""
    chat = message.chat
    name = message.chat.first_name

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    button_check = types.KeyboardButton('/check')
    keyboard.add(button_check)

    bot.send_message(
        chat_id=chat.id,
        text=f'Привет, {name}.',
        reply_markup=keyboard,
    )


@bot.message_handler(commands=['check'])
def temp(message):
    """Ручная проверка почты."""
    chat = message.chat

    if chat.id != MY_TELEGRAMM_ID:
        bot.send_message(
            chat_id=chat.id,
            text=f'Твой id - {chat.id}. У тебя нет доступа!'
        )
    bot.send_message(chat.id, 'Читаю почту...')
    imap = imap_connect()
    uid_list = get_uid_list(imap)

    if len(uid_list) == 0:
        bot.send_message(
            chat_id=MY_TELEGRAMM_ID,
            text='У вас нет новых сообщений.'
        )

    bot.send_message(
        chat_id=MY_TELEGRAMM_ID,
        text=f'У тебя {len(uid_list)} непрочитанных сообщений.'
    )

    for uid in uid_list:
        message = read_headers_message(uid, imap)
        keyboard = types.InlineKeyboardMarkup()
        btn_read = types.InlineKeyboardButton(
            '📖 Прочитать',
            callback_data=f'read_{uid}'
        )
        keyboard.add(btn_read)
        bot.send_message(
            chat_id=MY_TELEGRAMM_ID,
            text=message,
            reply_markup=keyboard
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith("read_"))
def read_letter(call):
    """Обработчик нажатия кнопки 'Прочитать'."""
    letter_id = call.data.split('_')[1]
    imap = imap_connect()
    letter = read_email_message(letter_id, imap)

    bot.send_message(
        chat_id=MY_TELEGRAMM_ID,
        text=letter
    )


bot.polling(interval=int(os.getenv('INTERVAL')))
