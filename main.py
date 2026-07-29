import os
import threading
import pandas as pd
import random
from flask import Flask
import telebot
from telebot import types

# --- 1. FLASK WEB SERVER (Keep-alive for Render) ---
app = Flask('')

@app.route('/')
def home():
    return "MLBB Tournament Bot is running!"

def run_web():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

t = threading.Thread(target=run_web, daemon=True)
t.start()

# --- 2. CONFIGURATION & SETUP ---
TOKEN = os.environ.get('BOT_TOKEN', '7850532150:AAHP9JuJZUZmTfGI6D7VQsNzy913mEX-yGQ')

ADMIN_ID = int(os.environ.get('ADMIN_ID', 7940654648))

FOLDER_RECEIPT = 'bien_lai'
EXCEL_FILE = 'danh_sach_giai_dau.xlsx'
QR_IMAGE_PATH = 'payment_qr.png'

excel_lock = threading.Lock()
bot = telebot.TeleBot(TOKEN)
user_states = {}

# Initialize Excel file structure
def init_excel():
    with excel_lock:
        if not os.path.exists(EXCEL_FILE):
            df = pd.DataFrame(columns=[
                'User_ID', 'Telegram_Username', 'IGN_ID_Captain', 
                'Name_Phone', 'Team_Members', 'Reg_Type', 'Status'
            ])
            df.to_excel(EXCEL_FILE, index=False)

init_excel()

# Save user entry to Excel
def save_to_excel(user_id, username, ign, contact, members, reg_type, status='Pending'):
    with excel_lock:
        try:
            if os.path.exists(EXCEL_FILE):
                df = pd.read_excel(EXCEL_FILE)
            else:
                df = pd.DataFrame(columns=[
                    'User_ID', 'Telegram_Username', 'IGN_ID_Captain', 
                    'Name_Phone', 'Team_Members', 'Reg_Type', 'Status'
                ])

            if user_id in df['User_ID'].values:
                df.loc[df['User_ID'] == user_id, [
                    'Telegram_Username', 'IGN_ID_Captain', 'Name_Phone', 
                    'Team_Members', 'Reg_Type', 'Status'
                ]] = [username, ign, contact, members, reg_type, status]
            else:
                new_row = pd.DataFrame({
                    'User_ID': [user_id],
                    'Telegram_Username': [username],
                    'IGN_ID_Captain': [ign],
                    'Name_Phone': [contact],
                    'Team_Members': [members],
                    'Reg_Type': [reg_type],
                    'Status': [status]
                })
                df = pd.concat([df, new_row], ignore_index=True)
            
            df.to_excel(EXCEL_FILE, index=False)
        except Exception as e:
            print(f"Excel saving error: {e}")

# Update approval status in Excel
def update_excel_status(user_id, status):
    with excel_lock:
        try:
            if os.path.exists(EXCEL_FILE):
                df = pd.read_excel(EXCEL_FILE)
                df.loc[df['User_ID'] == int(user_id), 'Status'] = status
                df.to_excel(EXCEL_FILE, index=False)
        except Exception as e:
            print(f"Excel status update error: {e}")

# --- 3. START COMMAND & MODE SELECTION ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('⚔️ Register Solo 1v1'))
    markup.add(types.KeyboardButton('🏆 Register 5v5 Team'))
    bot.send_message(
        message.chat.id,
        "🎮 **Welcome to MLBB KH Tournament!**\nPlease select your registration mode below:",
        parse_mode='Markdown',
        reply_markup=markup
    )

@bot.message_handler(func=lambda msg: msg.text in ['⚔️ Register Solo 1v1', '🏆 Register 5v5 Team'])
def handle_registration_choice(message):
    reg_type = 'Solo 1v1' if 'Solo' in message.text else 'Team 5v5'
    user_states[message.from_user.id] = {
        'reg_type': reg_type, 
        'step': 'waiting_for_ign'
    }
    
    if reg_type == 'Solo 1v1':
        prompt = (
            "📝 You selected **Solo 1v1**.\n\n"
            "1️⃣ Please enter your **In-Game Name (IGN) and Game ID**:\n"
            "*(e.g., LegendPlayer #123456)*\n\n"
            "⚠️ *Important: Please enter real IGN and ID for prize distribution!*"
        )
    else:
        prompt = (
            "📝 You selected **Team 5v5**.\n\n"
            "1️⃣ Please enter **Team Captain's IGN and Game ID**:\n"
            "*(e.g., CaptainPro #123456)*\n\n"
            "⚠️ *Important: Please enter real IGN and ID for prize distribution!*"
        )
    
    bot.reply_to(message, prompt, parse_mode='Markdown')

# --- 4. STEP-BY-STEP INPUT HANDLING ---
@bot.message_handler(func=lambda msg: msg.from_user.id in user_states and msg.content_type == 'text')
def handle_text_steps(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    step = state.get('step')

    # STEP 1: Save IGN -> Ask for Real Name & Phone
    if step == 'waiting_for_ign':
        state['ign'] = message.text
        state['step'] = 'waiting_for_contact'
        bot.reply_to(
            message,
            "2️⃣ Please enter your **Full Name & Real Phone Number**:\n"
            "*(e.g., Sokha Chan - 012 345 678)*\n\n"
            "*(This will be saved to contact you for tournament details)*",
            parse_mode='Markdown'
        )

    # STEP 2: Save Contact Info
    elif step == 'waiting_for_contact':
        state['contact'] = message.text
        
        # If Solo 1v1 -> Proceed directly to payment QR
        if state['reg_type'] == 'Solo 1v1':
            state['members'] = 'N/A'
            send_payment_qr(message, user_id)
        # If Team 5v5 -> Ask for the other 4 team members
        else:
            state['step'] = 'waiting_for_members'
            bot.reply_to(
                message,
                "3️⃣ Please enter the **IGN and Game IDs of the 4 other Team Members**:\n"
                "*(Format: Member 2, Member 3, Member 4, Member 5)*\n\n"
                "⚠️ *Important: All IGNs & IDs must be accurate for prize distribution!*",
                parse_mode='Markdown'
            )

    # STEP 3 (5v5 Only): Save Members -> Send Payment QR
    elif step == 'waiting_for_members':
        state['members'] = message.text
        send_payment_qr(message, user_id)

# Send ABA Payment QR Code with instructions
def send_payment_qr(message, user_id):
    user_states[user_id]['step'] = 'waiting_for_receipt'
    caption_text = (
        "📸 **PAYMENT INSTRUCTIONS**\n\n"
        "Please scan the QR code above to pay the entry fee.\n\n"
        "After payment is complete, **send a screenshot of your payment receipt (photo)** here to finish registration."
    )
    
    if os.path.exists(QR_IMAGE_PATH):
        try:
            bot.send_photo(
                message.chat.id,
                open(QR_IMAGE_PATH, 'rb'),
                caption=caption_text,
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Error sending QR image: {e}")
            bot.send_message(message.chat.id, caption_text, parse_mode='Markdown')
    else:
        bot.send_message(
            message.chat.id,
            "⚠️ *(Payment QR Image not found)*\n\n" + caption_text,
            parse_mode='Markdown'
        )

# --- 5. RECEIPT SUBMISSION HANDLING ---
@bot.message_handler(content_types=['photo'])
def handle_receipt(message):
    user_id = message.from_user.id
    
    if user_id not in user_states or user_states[user_id].get('step') != 'waiting_for_receipt':
        bot.reply_to(message, "⚠️ Please type /start to begin registration first.")
        return

    state = user_states[user_id]
    username = message.from_user.username or message.from_user.first_name or str(user_id)
    ign = state.get('ign', 'Unknown')
    contact = state.get('contact', 'Unknown')
    members = state.get('members', 'N/A')
    reg_type = state.get('reg_type', 'Solo 1v1')
    
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    if not os.path.exists(FOLDER_RECEIPT):
        os.makedirs(FOLDER_RECEIPT, exist_ok=True)
        
    img_path = os.path.join(FOLDER_RECEIPT, f'{user_id}.jpg')
    with open(img_path, 'wb') as new_file:
        new_file.write(downloaded_file)

    save_to_excel(user_id, username, ign, contact, members, reg_type, status='Pending')

    markup = types.InlineKeyboardMarkup()
    btn_approve = types.InlineKeyboardButton('✅ Approve', callback_data=f'FA:{user_id}')
    btn_reject = types.InlineKeyboardButton('❌ Reject', callback_data=f'RJ:{user_id}')
    markup.add(btn_approve, btn_reject)

    caption = (
        f"🚨 **NEW REGISTRATION SUBMITTED!**\n"
        f"-------------------------\n"
        f"📌 **Type:** {reg_type}\n"
        f"👤 **Telegram:** @{username} (`{user_id}`)\n"
        f"🎮 **IGN/ID:** {ign}\n"
        f"📞 **Name & Phone:** {contact}\n"
    )
    if reg_type == 'Team 5v5':
        caption += f"👥 **Team Members:** {members}\n"

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
        '⏳ **Your payment receipt has been received!**\nPlease wait a moment while the organizer verifies your registration.',
        parse_mode='Markdown'
    )
    user_states.pop(user_id, None)

# --- 6. ADMIN CALLBACK HANDLER ---
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
        update_excel_status(target_user_id, 'Approved')
        bot.answer_callback_query(call.id, '✅ Approved successfully!')
        try:
            bot.send_message(
                target_user_id,
                '🎉 **Congratulations! Your registration has been approved.**\nWelcome to the tournament! Good luck and have fun!',
                parse_mode='Markdown',
            )
        except Exception as e:
            print(f"Error notifying user {target_user_id}: {e}")
    else:
        update_excel_status(target_user_id, 'Rejected')
        bot.answer_callback_query(call.id, '❌ Rejected.')
        try:
            bot.send_message(
                target_user_id,
                '❌ **Your registration receipt was rejected.**\nPlease contact the organizer for support.',
                parse_mode='Markdown',
            )
        except Exception as e:
            print(f"Error notifying user {target_user_id}: {e}")

# --- 7. AUTO-PAIRING FEATURE FOR ADMIN ---
@bot.message_handler(commands=['ghepcap_solo', 'ghepcap_team'])
def auto_pairing(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ This command is for Admins only.")
        return

    reg_type = 'Solo 1v1' if 'ghepcap_solo' in message.text else 'Team 5v5'
    
    with excel_lock:
        try:
            if not os.path.exists(EXCEL_FILE):
                bot.reply_to(message, "⚠️ No registration data found.")
                return

            df = pd.read_excel(EXCEL_FILE)
            valid_players = df[(df['Reg_Type'] == reg_type) & (df['Status'] == 'Approved')]['IGN_ID_Captain'].tolist()

            if len(valid_players) < 2:
                bot.reply_to(message, f"⚠️ Not enough approved players/teams for {reg_type} (At least 2 required).")
                return

            random.shuffle(valid_players)

            pairing_text = f"⚔️ **TOURNAMENT MATCH PAIRINGS ({reg_type})** ⚔️\n\n"
            match_idx = 1
            
            for i in range(0, len(valid_players) - 1, 2):
                pairing_text += f"Match {match_idx}: **{valid_players[i]}** vs **{valid_players[i+1]}**\n"
                match_idx += 1

            if len(valid_players) % 2 != 0:
                pairing_text += f"\n📌 Bye / Waiting Player/Team: **{valid_players[-1]}**"

            bot.send_message(message.chat.id, pairing_text, parse_mode='Markdown')

        except Exception as e:
            bot.reply_to(message, f"❌ Error reading pairing data: {e}")

# --- 8. BOT LAUNCH ---
if __name__ == '__main__':
    print("Starting MLBB Tournament Bot...")
    try:
        bot.remove_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"Error clearing webhook: {e}")
        
    bot.infinity_polling(skip_pending=True)
                
