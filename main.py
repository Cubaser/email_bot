import os
from datetime import datetime

import email
import imaplib
import os
from email.header import decode_header

from bs4 import BeautifulSoup
from dotenv import load_dotenv

from telebot import TeleBot, types
from dotenv import load_dotenv

load_dotenv()

MY_TELEGRAMM_ID = int(os.getenv('MY_TELEGRAMM_ID'))
mail_pass = os.getenv('MAIL_PASS')
username = os.getenv('MAIL_USER')
imap_server = os.getenv('MAIL_SERVICE')


imap = imaplib.IMAP4_SSL(imap_server)
imap.login(username, mail_pass)
bot = TeleBot(os.getenv('BOT_TOKEN'))


def get_uid_list(imap):
    imap.select("INBOX")
    response = imap.uid('search', "UNSEEN", "ALL")
    if response[0] == 'OK':
        uid_list = response[1][0].decode().split()

    return uid_list


def convert_text(msg):

    for part in msg.walk():
        content_type = part.get_content_type()

        if content_type == "text/plain" or content_type == "text/html":
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or 'utf-8'

            if payload:
                text = payload.decode(charset, errors="ignore")
                soup = BeautifulSoup(text, "lxml")
                clean_text = soup.get_text(separator="\n", strip=True)

    return clean_text


def read_email_message(uid):
    res, msg = imap.uid('fetch', uid, '(RFC822)')
    if res != 'OK':
        return f'Не смог прочитать сообщение {uid}'

    msg = email.message_from_bytes(msg[0][1])

    # Получаем дату письма
    letter_date_tuple = email.utils.parsedate_tz(msg["Date"])
    if letter_date_tuple:
        # Конвертируем в datetime
        dt = datetime(*letter_date_tuple[:6])
        # Форматируем в нужный вид
        letter_date = dt.strftime("%d.%m.%Y %H:%M")
    else:
        letter_date = "Неизвестная дата"

    # Получаем имя и email отправителя
    raw_from = msg["From"]
    decoded_from, encoding = decode_header(raw_from)[0]
    # Если надо декодируем
    if isinstance(decoded_from, bytes):
        decoded_from = decoded_from.decode(encoding or "utf-8")
    sender_name, sender_email = email.utils.parseaddr(decoded_from)
    # Если есть имя, то используем его, иначе просто email
    letter_from = f"{sender_name} <{sender_email}>" if sender_name else sender_email

    # Получаем тему письма 
    letter_title, encoding = decode_header(msg["Subject"])[0]
    # Если надо декодируем
    if isinstance(letter_title, bytes):
        letter_title = letter_title.decode(encoding or "utf-8")

    letter_text = convert_text(msg)

    message = f'📧 Тема письма: {letter_title} \n'
    message += f'👤 Отправитель: {letter_from} \n'
    message += f'📅 Дата отправки: {letter_date} \n'
    message += f'📝 Текст письма:\n {letter_text}'

    return message


@bot.message_handler(commands=['start'])
def wake_up(message):
    chat = message.chat
    name = message.chat.first_name

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    button_check = types.KeyboardButton('/check')
    button_read = types.KeyboardButton('/read')
    keyboard.add(button_check, button_read)

    bot.send_message(
        chat_id=chat.id,
        text=f'Привет, {name}.',
        reply_markup=keyboard,
    )


@bot.message_handler(commands=['check'])
def check(message):
    chat = message.chat
    if chat.id != MY_TELEGRAMM_ID:
        bot.send_message(
            chat_id=chat.id,
            text=f'Твой id - {chat.id}. У тебя нет доступа!'
        )
    bot.send_message(chat.id, "Читаю почту...")
    uid_list = get_uid_list(imap)
    print(uid_list)

    bot.send_message(
            chat_id=chat.id,
            text=f'У тебя {len(uid_list)} непрочитанных сообщений.'
        )



@bot.message_handler(commands=['read'])
def read(message):
    chat = message.chat
    if chat.id != MY_TELEGRAMM_ID:
        bot.send_message(
            chat_id=chat.id,
            text=f'Твой id - {chat.id}. У тебя нет доступа!'
        )
    bot.send_message(chat.id, "Читаю почту...")
    #uid_list = get_uid_list(imap)
    get_uid_list(imap)

    uid_list = ['36033', '36040', '36042', '36060']

    if len(uid_list) == 0:
        bot.send_message(
            chat_id=chat.id,
            text='У вас нет новых сообщений.'
        )

    for uid in uid_list:
        message = read_email_message(uid)

        bot.send_message(
            chat_id=chat.id,
            text=message
        )


bot.polling(interval=int(os.getenv('INTERVAL')))
