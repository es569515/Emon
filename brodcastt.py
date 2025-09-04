import logging
import time
import re
import json
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler
)

# Bot Configuration
BOT_TOKEN = "YOUR"
ADMIN_ID = YOUR_ADMIN_ID_HERE

# Conversation states
WAITING_FOR_MEDIA, WAITING_FOR_BUTTONS = range(2)

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# File to store groups data
GROUPS_FILE = "groups.json"

def load_groups():
    """Load groups from file"""
    if os.path.exists(GROUPS_FILE):
        try:
            with open(GROUPS_FILE, 'r') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_groups(groups):
    """Save groups to file"""
    with open(GROUPS_FILE, 'w') as f:
        json.dump(list(groups), f)

# Load groups at startup
active_groups = load_groups()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⚠️ You are not authorized to use this bot!")
        return
    
    keyboard = [[InlineKeyboardButton("📢 Broadcast", callback_data='broadcast')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Welcome to Admin Panel!\nTracked groups: {len(active_groups)}\nClick Broadcast to send a message to all groups.",
        reply_markup=reply_markup
    )

async def track_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track groups where the bot is added"""
    if update.message.chat.type in ['group', 'supergroup']:
        group_id = update.message.chat.id
        if group_id not in active_groups:
            active_groups.add(group_id)
            save_groups(active_groups)  # Save to file
            logger.info(f"New group added: {group_id}")
            
            # Send notification to admin
            await context.bot.send_message(
                chat_id=ADMIN_ID, 
                text=f"✅ Bot added to new group:\nID: {group_id}\nTotal groups: {len(active_groups)}"
            )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'broadcast':
        if len(active_groups) == 0:
            await query.edit_message_text("❌ No groups tracked yet. Add the bot to some groups first.")
            return ConversationHandler.END
            
        context.user_data['broadcast_data'] = {}
        await query.edit_message_text("📢 Broadcast Mode:\nPlease send your message (text, photo, or any media)")
        return WAITING_FOR_MEDIA

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    # Process message
    message = update.message
    broadcast_data = context.user_data['broadcast_data']
    
    if message.text:
        broadcast_data['type'] = 'text'
        broadcast_data['content'] = message.text
        broadcast_data['caption'] = ""
    elif message.photo:
        broadcast_data['type'] = 'photo'
        broadcast_data['content'] = message.photo[-1].file_id
        broadcast_data['caption'] = message.caption or ""
    elif message.document:
        broadcast_data['type'] = 'document'
        broadcast_data['content'] = message.document.file_id
        broadcast_data['caption'] = message.caption or ""
    elif message.video:
        broadcast_data['type'] = 'video'
        broadcast_data['content'] = message.video.file_id
        broadcast_data['caption'] = message.caption or ""
    else:
        await update.message.reply_text("❌ Unsupported media type. Please send text, photo, video, or document.")
        return WAITING_FOR_MEDIA
    
    # Ask if user wants to add buttons
    keyboard = [
        [InlineKeyboardButton("✅ Add URL Buttons", callback_data='add_buttons')],
        [InlineKeyboardButton("➡️ Skip Buttons", callback_data='no_buttons')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        "Would you like to add inline URL buttons to your message?",
        reply_markup=reply_markup
    )
    
    return WAITING_FOR_BUTTONS

async def handle_buttons_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'add_buttons':
        await query.edit_message_text(
            "Please send button data in this format:\n\n"
            "Button Text - https://example.com\n"
            "Another Button - https://another-example.com\n\n"
            "You can add multiple buttons (one per line).\n"
            "Send /skip if you don't want to add any buttons."
        )
        return WAITING_FOR_BUTTONS
    else:
        # No buttons, proceed with broadcast
        context.user_data['broadcast_data']['buttons'] = None
        await query.edit_message_text("📤 Sending broadcast to all groups...")
        await send_broadcast(update, context)
        return ConversationHandler.END

async def handle_button_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    if update.message.text == '/skip':
        context.user_data['broadcast_data']['buttons'] = None
        await update.message.reply_text("📤 Sending broadcast without buttons...")
        await send_broadcast(update, context)
        return ConversationHandler.END
    
    button_text = update.message.text
    buttons = []
    
    # Parse button data
    for line in button_text.split('\n'):
        line = line.strip()
        if line and ' - ' in line:
            parts = line.split(' - ', 1)
            if len(parts) == 2:
                text, url = parts
                text = text.strip()
                url = url.strip()
                
                # Validate URL format
                if re.match(r'^https?://', url):
                    buttons.append([InlineKeyboardButton(text, url=url)])
                else:
                    await update.message.reply_text(
                        f"Invalid URL format: {url}\n"
                        "URLs must start with http:// or https://\n"
                        "Please send the buttons again or use /skip to skip buttons."
                    )
                    return WAITING_FOR_BUTTONS
    
    if not buttons:
        await update.message.reply_text(
            "No valid buttons found. Please use the format:\n\n"
            "Button Text - https://example.com\n\n"
            "Or send /skip to skip adding buttons."
        )
        return WAITING_FOR_BUTTONS
    
    context.user_data['broadcast_data']['buttons'] = buttons
    
    # Show preview of buttons
    preview_text = "✅ Buttons added:\n"
    for i, button in enumerate(buttons, 1):
        preview_text += f"{i}. {button[0].text} - {button[0].url}\n"
    
    preview_text += "\n📤 Sending broadcast..."
    await update.message.reply_text(preview_text)
    await send_broadcast(update, context)
    
    return ConversationHandler.END

async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        broadcast_data = context.user_data.get('broadcast_data', {})
        
        if not broadcast_data:
            await context.bot.send_message(chat_id=ADMIN_ID, text="❌ Error: No broadcast data found.")
            return
        
        # Create keyboard if buttons exist
        reply_markup = None
        if broadcast_data.get('buttons'):
            reply_markup = InlineKeyboardMarkup(broadcast_data['buttons'])
        
        # Send to all active groups
        success_count = 0
        failed_count = 0
        failed_details = []
        
        # Send progress message
        progress_message = await context.bot.send_message(
            chat_id=ADMIN_ID, 
            text=f"📤 Starting broadcast to {len(active_groups)} groups..."
        )
        
        # Send to all groups where the bot is active
        for i, group_id in enumerate(active_groups):
            try:
                if broadcast_data['type'] == 'text':
                    await context.bot.send_message(
                        chat_id=group_id, 
                        text=broadcast_data['content'],
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                elif broadcast_data['type'] == 'photo':
                    await context.bot.send_photo(
                        chat_id=group_id, 
                        photo=broadcast_data['content'],
                        caption=broadcast_data.get('caption', ''),
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                elif broadcast_data['type'] == 'document':
                    await context.bot.send_document(
                        chat_id=group_id, 
                        document=broadcast_data['content'],
                        caption=broadcast_data.get('caption', ''),
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                elif broadcast_data['type'] == 'video':
                    await context.bot.send_video(
                        chat_id=group_id, 
                        video=broadcast_data['content'],
                        caption=broadcast_data.get('caption', ''),
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                
                success_count += 1
                logger.info(f"Message sent to group: {group_id}")
                
                # Update progress every 5 groups
                if (i + 1) % 5 == 0:
                    await context.bot.edit_message_text(
                        chat_id=ADMIN_ID,
                        message_id=progress_message.message_id,
                        text=f"📤 Sent to {i+1}/{len(active_groups)} groups...\n✅ {success_count} successful, ❌ {failed_count} failed"
                    )
                
            except Exception as e:
                failed_count += 1
                error_msg = str(e)
                failed_details.append(f"Group {group_id}: {error_msg}")
                logger.error(f"Failed to send to group {group_id}: {e}")
                
                # Check if it's a restriction issue :cite[1]
                if "restricted" in error_msg.lower() or "blocked" in error_msg.lower():
                    # Remove restricted group from active groups
                    active_groups.discard(group_id)
                    save_groups(active_groups)
                    logger.info(f"Removed restricted group: {group_id}")
        
        # Update final progress
        await context.bot.edit_message_text(
            chat_id=ADMIN_ID,
            message_id=progress_message.message_id,
            text=f"✅ Broadcast completed!\n📊 Sent to {success_count} groups, failed: {failed_count}"
        )
        
        # Send detailed report
        report_text = f"""
📊 Broadcast Report:

✅ Successfully sent: {success_count}
❌ Failed: {failed_count}
📋 Total groups: {len(active_groups)}
        """
        
        if failed_details:
            failed_details_str = "\n".join(failed_details[:5])  # Show first 5 errors only
            if len(failed_details) > 5:
                failed_details_str += f"\n... and {len(failed_details) - 5} more errors"
            report_text += f"\n❌ Errors:\n{failed_details_str}"
        
        await context.bot.send_message(chat_id=ADMIN_ID, text=report_text)
        
        # Clear conversation data
        if 'broadcast_data' in context.user_data:
            context.user_data.pop('broadcast_data')
            
    except Exception as e:
        logger.error(f"Error in send_broadcast: {e}")
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Error during broadcast: {str(e)}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    if 'broadcast_data' in context.user_data:
        context.user_data.pop('broadcast_data')
    await update.message.reply_text("❌ Broadcast cancelled.")
    return ConversationHandler.END

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Conversation handler for broadcast
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern='^broadcast$')],
        states={
            WAITING_FOR_MEDIA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Chat(chat_id=ADMIN_ID), handle_media),
                MessageHandler((filters.PHOTO | filters.VIDEO | filters.Document.ALL) & filters.Chat(chat_id=ADMIN_ID), handle_media),
                CommandHandler('cancel', cancel)
            ],
            WAITING_FOR_BUTTONS: [
                CallbackQueryHandler(handle_buttons_decision, pattern='^(add_buttons|no_buttons)$'),
                MessageHandler(filters.TEXT & filters.Chat(chat_id=ADMIN_ID), handle_button_data),
                CommandHandler('cancel', cancel)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.ALL & filters.ChatType.GROUPS, track_group))
    application.add_handler(conv_handler)
    
    # Start bot
    application.run_polling()
    logger.info("Bot is running!")

if __name__ == '__main__':
    main()
