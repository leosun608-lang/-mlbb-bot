import os
import threading
from flask import Flask
import telebot
from telebot import types

# --- 1. FLASK WEB SERVER (Duy trì bot trên Render) ---
app = Flask('')


@app.route('/')
def home():
  return 'Bot is running!'


def run_web():
  port = int(os.environ.get('PORT', 10000))
  app.run(host='0.0.0.0', port=port)


t = threading.Thread(target=run_web)
t.start()

# --- 2. CẤU HÌNH BOT ---
TOKEN = 'ĐIỀN_TOKEN_BOT_CỦA_BẠN_VÀO_ĐÂY'
ADMIN_ID = (  # Điền Telegram ID của Admin vào đây
    123456789
)
RECEIPTS_DIR = 'receipts'

bot = telebot.TeleBot(TOKEN)
pending_review = {}


# --- 3. XỬ LÝ KHI NGƯỜI CHƠI GỬI ẢNH BIÊN LAI ---
@bot.message_handler(content_types=['photo'])
def handle_receipt(message):
  user_id = message.from_user.id
  username = (
      message.from_user.username
      or message.from_user.first_name
      or str(user_id)
  )

  # Lấy file ảnh lớn nhất người chơi vừa gửi
  file_info = bot.get_file(message.photo[-1].file_id)
  downloaded_file = bot.download_file(file_info.file_path)

  if not os.path.exists(RECEIPTS_DIR):
    os.makedirs(RECEIPTS_DIR)
  img_path = os.path.join(RECEIPTS_DIR, f'{user_id}.jpg')
  with open(img_path, 'wb') as new_file:
    new_file.write(downloaded_file)

  # Lưu thông tin tạm thời để Admin duyệt
  pending_review[str(user_id)] = {
      'uid': user_id,
      'data': username,
      'reg_type': 'solo',
      'file_id': message.photo[-1].file_id,
  }

  # Tạo bàn phím Inline cho Admin (Dùng định dạng FA: / RJ:)
  markup = types.InlineKeyboardMarkup()
  btn_approve = types.InlineKeyboardButton(
      '✅ Approve', callback_data=f'FA:{user_id}'
  )
  btn_reject = types.InlineKeyboardButton(
      '❌ Reject', callback_data=f'RJ:{user_id}'
  )
  markup.add(btn_approve, btn_reject)

  # Gửi ảnh và nút bấm về tài khoản Admin
  caption = (
      f'📥 **New receipt to review!**\n- Sender: @{username}\n- ID:'
      f' `{user_id}`'
  )
  try:
    bot.send_photo(
        ADMIN_ID,
        open(img_path, 'rb'),
        caption=caption,
        parse_mode='Markdown',
        reply_markup=markup,
    )
  except Exception as e:
    print(f'Error sending to admin: {e}')

  # Phản hồi lại cho người chơi
  bot.reply_to(
      message,
      '⏳ Your payment receipt has been sent to the organizers. Please wait a'
      ' moment for verification!',
  )


# --- 4. XỬ LÝ NÚT BẤM DUYỆT CỦA ADMIN ---
@bot.callback_query_handler(func=lambda c: c.data.startswith(('FA:', 'RJ:')))
def admin_callback(call):
  if call.from_user.id != ADMIN_ID:
    bot.answer_callback_query(call.id, '⛔ Admins only.', show_alert=True)
    return

  action, token = call.data.split(':', 1)
  review = pending_review.pop(token, None)

  if review is None:
    bot.answer_callback_query(
        call.id, '⚠️ This review has already been processed.', show_alert=True
    )
    bot.edit_message_reply_markup(
        call.message.chat.id, call.message.message_id, reply_markup=None
    )
    return

  bot.edit_message_reply_markup(
      call.message.chat.id, call.message.message_id, reply_markup=None
  )

  if action == 'FA':
    bot.answer_callback_query(call.id, '✅ Approved successfully!')
    bot.send_message(
        review['uid'],
        '🎉 **Your registration has been approved!** Welcome to the'
        ' tournament.',
        parse_mode='Markdown',
    )
  else:
    bot.answer_callback_query(call.id, '❌ Rejected.')
    bot.send_message(
        review['uid'],
        '❌ **Your receipt was rejected.** Please contact the organizer for'
        ' support.',
        parse_mode='Markdown',
    )


# --- KHỞI CHẠY BOT ---
if __name__ == '__main__':
  bot.infinity_polling()
  
