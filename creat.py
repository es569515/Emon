import asyncio
import calendar
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.functions.channels import CreateChannelRequest, InviteToChannelRequest, EditAdminRequest
from telethon.tl.types import InputPeerChannel, ChatAdminRights, InputPeerUser

# ------------------------------
# CONFIG - Replace with your info
# ------------------------------
api_id = 20505183                # <-- Your API ID
api_hash = '935939ffdecb9d95d67278af3bdbc971'     # <--> Your API Hash
phone_number = '+8801714636409'   # <-- Your phone number

# Bots to add to each group
bots = [
    '@youyou2323bot',
]

# Number of groups to create
number_of_groups = 50

# Interval settings (in seconds)
interval_between_bots = 1
interval_between_groups = 10
retry_interval = 3
# ------------------------------

client = TelegramClient('session_name', api_id, api_hash)

async def add_bot_and_make_admin(chat_peer, bot_name):
    """Add bot and make admin with retry"""
    while True:
        try:
            # Resolve bot username to get its entity
            bot_entity = await client.get_input_entity(bot_name)
            
            # Add bot to channel
            await client(InviteToChannelRequest(chat_peer, [bot_entity]))
            await asyncio.sleep(1)  # small wait before making admin

            # Make bot admin with all rights
            rights = ChatAdminRights(
                change_info=True,
                post_messages=True,
                edit_messages=True,
                delete_messages=True,
                ban_users=True,
                invite_users=True,
                pin_messages=True,
                add_admins=True,
                manage_call=True  # Added this for completeness
            )
            await client(EditAdminRequest(chat_peer, bot_entity, rights, 'Bot'))
            print(f"Added and made admin: {bot_name}")
            break
        except Exception as e:
            print(f"Error with bot {bot_name}: {e}. Retrying in {retry_interval} seconds...")
            await asyncio.sleep(retry_interval)

async def main():
    await client.start(phone=phone_number)

    # Get current month and year (like "August 2025")
    now = datetime.now()
    month_year = f"{calendar.month_name[now.month]} {now.year}"

    for i in range(number_of_groups):
        group_name = f"{month_year} Group {i+1}"
        try:
            # Create private megagroup
            result = await client(CreateChannelRequest(
                title=group_name,
                about='Auto created private group',
                megagroup=True
            ))

            chat = result.chats[0]
            chat_peer = InputPeerChannel(chat.id, chat.access_hash)
            print(f"Created private group: {group_name} (ID: {chat.id})")

            # Add bots one by one and make them admin
            for bot in bots:
                await add_bot_and_make_admin(chat_peer, bot)
                await asyncio.sleep(interval_between_bots)

            # Wait before creating the next group
            await asyncio.sleep(interval_between_groups)

        except Exception as e:
            print(f"Error creating group {group_name}: {e}")
            await asyncio.sleep(interval_between_groups)

    print("Finished creating groups!")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())