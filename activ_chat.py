# meta developer: @lir1mod

import time
from telethon import TelegramClient
from telethon.tl.types import Message
from .. import loader, utils

@loader.tds
class ChatActivityMod(loader.Module):
    """Знайти головних спамерів"""

    strings = {
        "name": "ChatActivity",
        "searching": (
            "<emoji document_id=5188311512791393083>🔎</emoji> <b>Шукаю найбільш активних"
            " користувачів у чаті...</b>"
        ),
        "user": (
            '<emoji document_id=5314541718312328811>👤</emoji> {}. <a href="{}">{}</a>: {} повідомлень'
        ),
        "admin_senior": "👑 {}. <a href='{}'>{}</a> (Старший адміністратор): {} повідомлень",
        "admin_junior": "🛡 {}. <a href='{}'>{}</a> (Молодший адміністратор): {} повідомлень",
        "regular": "👤 {}. <a href='{}'>{}</a>: {} повідомлень",
        "active": (
            "<emoji document_id=5312361425409156767>⬆️</emoji> <b>Найбільш активні користувачі у чаті:</b>\n\n"
            "<b>Адміністратори:</b>\n{}\n\n<b>Звичайні користувачі:</b>\n{}\n\n<i>Запит виконався за: {} секунд</i>"
        ),
        "_cmd_doc_activchat": "Знаходить топ-40 активних користувачів (спамерів) у чаті.",
        "_cls_doc": "Модуль для аналізу активності користувачів у чаті.",
    }

    async def get_active_participants(self, client: TelegramClient, chat_id):
        active_users = {}
        async for participant in client.iter_participants(chat_id):
            if not participant.bot:  
                active_users[participant.id] = participant
        return active_users

    async def get_admin_status(self, client: TelegramClient, chat_id, user_id):
        try:
            member = await client.get_permissions(chat_id, user_id)
            if member.is_admin:
                if member.ban_users or member.add_admins:
                    return "senior"  
                else:
                    return "junior"  
        except Exception:
            return None  
          
    async def count_messages(self, client: TelegramClient, chat_id, active_users, limit=None):
        user_message_count = {}
        async for msg in client.iter_messages(chat_id, limit=limit):
            user_id = msg.sender_id
            if user_id and user_id in active_users:
                user_message_count[user_id] = user_message_count.get(user_id, 0) + 1
        return user_message_count

    @loader.command("activchat", description="Знаходить топ-40 активних користувачів (спамерів) у чаті.")
    async def activchat(self, message: Message):
        """[кількість] [-m <int>] - Знаходить топ-40 спамерів у чаті."""
        client = message.client  
        args = utils.get_args_raw(message)
        limit = None

        if "-m" in args:
            limit = int("".join([lim for lim in args[args.find("-m") + 2:] if lim.isdigit()]))
            args = args[: args.find("-m")].strip()

        quantity = int(args) if args.isdigit() else 40  

        search_message = await client.send_message(message.peer_id, self.strings["searching"])

        await message.delete()

        start_time = time.perf_counter()

        chat_id = message.peer_id
        active_users = await self.get_active_participants(client, chat_id)

        user_message_count = await self.count_messages(client, chat_id, active_users, limit)

        sorted_users = sorted(user_message_count.items(), key=lambda x: x[1], reverse=True)

        admins_senior = []
        admins_junior = []
        regular_users = []

        for i, (user_id, count) in enumerate(sorted_users[:quantity]):
            user = active_users[user_id]
            admin_status = await self.get_admin_status(client, chat_id, user_id)

            if admin_status == "senior":
                admins_senior.append(self.strings["admin_senior"].format(i + 1, user.username, user.first_name, count))
            elif admin_status == "junior":
                admins_junior.append(self.strings["admin_junior"].format(i + 1, user.username, user.first_name, count))
            else:
                regular_users.append(self.strings["regular"].format(i + 1, user.username, user.first_name, count))

        admins_column = "\n".join(admins_senior + admins_junior) if (admins_senior or admins_junior) else "Немає адміністраторів"
        regular_column = "\n".join(regular_users) if regular_users else "Немає звичайних користувачів"

        await search_message.edit(
            self.strings["active"].format(
                admins_column, regular_column, round(time.perf_counter() - start_time, 2)
            )
        )
