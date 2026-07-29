import os
import threading
import pandas as pd
import random
from flask import Flask
import telebot
from telebot import types

# --- 1. FLASK WEB SERVER (Duy trì bot hoạt động trên Render) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot MLBB Tournament đang hoạt động!"

def run_web():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

t = threading.Thread(target=run_web, daemon=True)
t.start()

# --- 2. CẤU HÌNH BOT ---
# Token mới nhất đã được cập nhật chính xác
TOKEN = os.environ.get('BOT_TOKEN', '7850532150:AAHnm2sAFBLj-msGXmKWadVkUpOm0gvXVmA')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 7940654648))

FOLDER_RECEIPT = 'bien_lai'
EXCEL_FILE = 'danh_sach_giai_dau.xlsx'

excel_lock = threading.Lock()  # Khóa an toàn chống xung đột file Excel
bot = telebot.TeleBot(TOKEN)
user_states = {}

# Khởi tạo file Excel nếu chưa tồn tại
def init_excel():
    with excel_lock:
        if not os.path.exists(EXCEL_FILE):
            df = pd.DataFrame(columns=['User_ID', 'Username', 'IGN', 'Loai_Dang_Ky', 'Trang_Thai'])
            df.to_excel(EXCEL_FILE, index=False)

init_excel()

# Hàm lưu dữ liệu người dùng vào file Excel
def save_to_excel(user_id, username, ign, reg_type, status='Cho_Duyet'):
    with excel_lock:
        try:
            if os.path.exists(EXCEL_FILE):
                df = pd.read_excel(EXCEL_FILE)
            else:
                df = pd.DataFrame(columns=['User_ID', 'Username', 'IGN', 'Loai_Dang_Ky', 'Trang_Thai'])

            if user_id in df['User_ID'].values:
                df.loc[df['User_ID'] == user_id, ['Username', 'IGN', 'Loai_Dang_Ky', 'Trang_Thai']] = [username, ign, reg_type, status]
            else:
                new_row = pd.DataFrame({'User_ID': [user_id], 'Username': [username], 'IGN': [ign], 'Loai_Dang_Ky': [reg_type], 'Trang_Thai': [status]})
                df = pd.concat([df, new_row], ignore_index=True)
            
            df.to_excel(EXCEL_FILE, index=False)
        except Exception as e:
            print(f"Lỗi lưu Excel: {e}")

# Cập nhật trạng thái duyệt vào file Excel
def update_excel_status(user_id, status):
    with excel_lock:
        try:
            if os.path.exists(EXCEL_FILE):
                df = pd.read_excel(EXCEL_FILE)
                df.loc[df['User_ID'] == int(user_id), 'Trang_Thai'] = status
                df.to_excel(EXCEL_FILE, index=False)
        except Exception as e:
            print(f"Lỗi cập nhật trạng thái Excel: {e}")

# --- 3. XỬ LÝ LỆNH /START & MENU KHỞI ĐỘNG ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('⚔️ Register Solo 1v1'))
    markup.add(types.KeyboardButton('🏆 Register 5v5 Team'))
    bot.send_message(
        message.chat.id,
        "🎮 **Welcome to MLBB KH Tournament!**\nPlease choose your registration category below:",
        parse_mode='Markdown',
        reply_markup=markup
    )

@bot.message_handler(func=lambda msg: msg.text in ['⚔️ Register Solo 1v1', '🏆 Register 5v5 Team'])
def handle_registration_choice(message):
    reg_type = 'Solo 1v1' if 'Solo' in message.text else 'Team 5v5'
    user_states[message.from_user.id] = {'reg_type': reg_type, 'step': 'waiting_for_ign'}
    bot.reply_to(message, f"📝 You selected **{reg_type}**.\nPlease enter your **IGN (In-Game Name)**:", parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[message.from_user.id].get('step') == 'waiting_for_ign')
def handle_ign(message):
    user_id = message.from_user.id
    ign = message.text
    user_states[user_id]['ign'] = ign
    user_states[user_id]['step'] = 'waiting_for_receipt'
    bot.reply_to(message, f"✅ IGN saved: **{ign}**\n\n📸 Now please send a screenshot of your payment receipt (photo).", parse_mode='Markdown')

# --- 4. XỬ LÝ KHI NGƯỜI CHƠI GỬI ẢNH BIÊN LAI ---
@bot.message_handler(content_types=['photo'])
def handle_receipt(message):
    user_id = message.from_user.id
    
    if user_id not in user_states:
        user_states[user_id] = {'reg_type': 'Solo 1v1', 'ign': message.from_user.first_name}
    
    state = user_states[user_id]
    username = message.from_user.username or message.from_user.first_name or str(user_id)
    ign = state.get('ign', 'Unknown')
    reg_type = state.get('reg_type', 'Solo 1v1')
    
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    if not os.path.exists(FOLDER_RECEIPT):
        os.makedirs(FOLDER_RECEIPT, exist_ok=True)
        
    img_path = os.path.join(FOLDER_RECEIPT, f'{user_id}.jpg')
    with open(img_path, 'wb') as new_file:
        new_file.write(downloaded_file)

    save_to_excel(user_id, username, ign, reg_type, status='Cho_Duyet')

    markup = types.InlineKeyboardMarkup()
    btn_approve = types.InlineKeyboardButton('✅ Chấp thuận', callback_data=f'FA:{user_id}')
    btn_reject = types.InlineKeyboardButton('❌ Từ chối', callback_data=f'RJ:{user_id}')
    markup.add(btn_approve, btn_reject)

    caption = (
        f"🚨 **Hóa đơn mới cần xem xét!**\n"
        f"- Người gửi: @{username}\n"
        f"- IGN: {ign}\n"
        f"- Loại: {reg_type}\n"
        f"- ID: `{user_id}`"
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

    bot.reply_to(
        message,
        '⏳ Your payment receipt has been sent to the organizers. Please wait a moment for verification.',
    )
    user_states.pop(user_id, None)

# --- 5. XỬ LÝ NÚT BẤM DUYỆT CỦA ADMIN ---
@bot.callback_query_handler(func=lambda c: c.data.startswith(('FA:', 'RJ:')))
def admin_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, '⛔ Admins only.', show_alert=True)
        return

    action, target_user_id = call.data.split(':', 1)

    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    if action == 'FA':
        update_excel_status(target_user_id, 'Da_Duyet')
        bot.answer_callback_query(call.id, '✅ Approved successfully!')
        try:
            bot.send_message(
                target_user_id,
                '✅ **Your registration has been approved!** Welcome to the tournament.',
                parse_mode='Markdown',
            )
        except Exception as e:
            print(f"Lỗi gửi tin nhắn cho user {target_user_id}: {e}")
    else:
        update_excel_status(target_user_id, 'Tu_Choi')
        bot.answer_callback_query(call.id, '❌ Rejected.')
        try:
            bot.send_message(
                target_user_id,
                '❌ **Your receipt was rejected.** Please contact the organizer for support.',
                parse_mode='Markdown',
            )
        except Exception as e:
            print(f"Lỗi gửi tin nhắn cho user {target_user_id}: {e}")

# --- 6. TÍNH NĂNG TỰ ĐỘNG GHÉP CẶP ĐẤU CHO ADMIN ---
@bot.message_handler(commands=['ghepcap_solo', 'ghepcap_team'])
def auto_pairing(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Lệnh này chỉ dành cho Admin.")
        return

    reg_type = 'Solo 1v1' if 'ghepcap_solo' in message.text else 'Team 5v5'
    
    with excel_lock:
        try:
            if not os.path.exists(EXCEL_FILE):
                bot.reply_to(message, "⚠️ Chưa có dữ liệu đăng ký.")
                return

            df = pd.read_excel(EXCEL_FILE)
            valid_players = df[(df['Loai_Dang_Ky'] == reg_type) & (df['Trang_Thai'] == 'Da_Duyet')]['IGN'].tolist()

            if len(valid_players) < 2:
                bot.reply_to(message, f"⚠️ Chưa đủ số lượng người chơi đã duyệt cho thể loại {reg_type} (Cần ít nhất 2).")
                return

            random.shuffle(valid_players)

            pairing_text = f"⚔️ **DANH SÁCH GHẾP CẶP ĐẤU ({reg_type})** ⚔️\n\n"
            match_idx = 1
            
            for i in range(0, len(valid_players) - 1, 2):
                pairing_text += f"Match {match_idx}: **{valid_players[i]}** vs **{valid_players[i+1]}**\n"
                match_idx += 1

            if len(valid_players) % 2 != 0:
                pairing_text += f"\n📌 Người chơi/Đội chờ (Bye): **{valid_players[-1]}**"

            bot.send_message(message.chat.id, pairing_text, parse_mode='Markdown')

        except Exception as e:
            bot.reply_to(message, f"❌ Lỗi khi đọc dữ liệu ghép cặp: {e}")

# --- 7. KHỞI CHẠY BOT (CHỐNG LỖI 409 & WEBHOOK KHÔNG TỚI) ---
if __name__ == '__main__':
    print("Đang khởi động Bot...")
    try:
        bot.remove_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"Lỗi khi xoá webhook: {e}")
        
    bot.infinity_polling(skip_pending=True)
                                                                                                       
