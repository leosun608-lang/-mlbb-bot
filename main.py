import os
import threading
import pandas as pd
from flask import Flask
import telebot
from telebot import types

# --- 1. FLASK WEB SERVER (Duy trì bot trên Render) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot quản lý giải đấu đang hoạt động!"

def run_web():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

t = threading.Thread(target=run_web)
t.start()

# --- 2. CẤU HÌNH BOT ---
TOKEN = '7850532150:AAFFPO5R9ZQb6c_mG7jLLSNz6zf-xzmjnAY'
ADMIN_ID = 7940654648  # ID Telegram của bạn

FOLDER_RECEIPT = 'bien_lai'
EXCEL_FILE = 'danh_sach_giai_dau.xlsx'

bot = telebot.TeleBot(TOKEN)
pending_review = {}
user_states = {}

# Khởi tạo file Excel nếu chưa có
def init_excel():
    if not os.path.exists(EXCEL_FILE):
        df = pd.DataFrame(columns=['User_ID', 'Username', 'IGN', 'Loai_Dang_Ky', 'Trang_Thai'])
        df.to_excel(EXCEL_FILE, index=False)

init_excel()

# Hàm lưu dữ liệu vào Excel
def save_to_excel(user_id, username, ign, reg_type, status='Cho_Duyet'):
    try:
        df = pd.read_excel(EXCEL_FILE)
        # Nếu user đã tồn tại thì cập nhật, chưa thì thêm mới
        if user_id in df['User_ID'].values:
            df.loc[df['User_ID'] == user_id, ['IGN', 'Loai_Dang_Ky', 'Trang_Thai']] = [ign, reg_type, status]
        else:
            new_row = pd.DataFrame({'User_ID': [user_id], 'Username': [username], 'IGN': [ign], 'Loai_Dang_Ky': [reg_type], 'Trang_Thai': [status]})
            df = pd.concat([df, new_row], ignore_index=True)
        df.to_excel(EXCEL_FILE, index=False)
    except Exception as e:
        print(f"Lỗi lưu Excel: {e}")

# Cập nhật trạng thái trong Excel khi Admin duyệt
def update_excel_status(user_id, status):
    try:
        df = pd.read_excel(EXCEL_FILE)
        df.loc[df['User_ID'] == int(user_id), 'Trang_Thai'] = status
        df.to_excel(EXCEL_FILE, index=False)
    except Exception as e:
        print(f"Lỗi cập nhật trạng thái Excel: {e}")

# --- 3. XỬ LÝ LỆNH /START & MENU ---
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
        os.makedirs(FOLDER_RECEIPT)
    img_path = os.path.join(FOLDER_RECEIPT, f'{user_id}.jpg')
    with open(img_path, 'wb') as new_file:
        new_file.write(downloaded_file)

    # Lưu thông tin tạm vào Excel với trạng thái chờ duyệt
    save_to_excel(user_id, username, ign, reg_type, status='Cho_Duyet')

    pending_review[str(user_id)] = {
        'uid': user_id,
        'data': username,
        'ign': ign,
        'reg_type': reg_type,
    }

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

    action, token = call.data.split(':', 1)
    review = pending_review.pop(token, None)

    if review is None:
        bot.answer_callback_query(call.id, '⚠️ This review has already been processed.')
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        return

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

    if action == 'FA':
        update_excel_status(token, 'Da_Duyet')
        bot.answer_callback_query(call.id, '✅ Approved successfully!')
        bot.send_message(
            review['uid'],
            '✅ **Your registration has been approved!** Welcome to the tournament.',
            parse_mode='Markdown',
        )
    else:
        update_excel_status(token, 'Tu_Choi')
        bot.answer_callback_query(call.id, '❌ Rejected.')
        bot.send_message(
            review['uid'],
            '❌ **Your receipt was rejected.** Please contact the organizer for support.',
            parse_mode='Markdown',
        )

# --- 6. TÍNH NĂNG TỰ ĐỘNG GHÉP CẶP ĐẤU CHO ADMIN ---
@bot.message_handler(commands=['ghepcap_solo', 'ghepcap_team'])
def auto_pairing(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Lệnh này chỉ dành cho Admin.")
        return

    reg_type = 'Solo 1v1' if 'ghepcap_solo' in message.text else 'Team 5v5'
    
    try:
        df = pd.read_excel(EXCEL_FILE)
        # Lọc ra những người đã được duyệt thanh toán thuộc thể loại tương ứng
        valid_players = df[(df['Loai_Dang_Ky'] == reg_type) & (df['Trang_Thai'] == 'Da_Duyet')]['IGN'].tolist()

        if len(valid_players) < 2:
            bot.reply_to(message, f"⚠️ Chưa đủ số lượng người chơi đã duyệt cho thể loại {reg_type} (Cần ít nhất 2).")
            return

        # Xáo trộn ngẫu nhiên danh sách người chơi
        import random
        random.shuffle(valid_players)

        pairing_text = f"⚔️ **DANH SÁCH GHẾP CẶP ĐẤU ({reg_type})** ⚔️\n\n"
        match_idx = 1
        
        # Ghép cặp 2 người/đội một
        for i in range(0, len(valid_players) - 1, 2):
            pairing_text += f"Match {match_idx}: **{valid_players[i]}** vs **{valid_players[i+1]}**\n"
            match_idx += 1

        # Nếu số lượng lẻ, người cuối cùng chờ vòng sau (bye)
        if len(valid_players) % 2 != 0:
            pairing_text += f"\n📌 Người chơi/Đội chờ (Bye): **{valid_players[-1]}**"

        bot.send_message(message.chat.id, pairing_text, parse_mode='Markdown')

    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi khi đọc dữ liệu ghép cặp: {e}")

# --- KHỞI CHẠY BOT ---
if __name__ == '__main__':
    bot.remove_webhook()
    bot.infinity_polling()
    
