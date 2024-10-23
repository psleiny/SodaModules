# meta developer: @lir1mod

import time
from pyrogram import Client, filters
from pyrogram.types import Message, ChatMember
from .. import loader, utils


@loader.tds
class ChatActivityMod(loader.Module):
    """Знаходить топ-40 активних користувачів (спамерів) у чаті, розділяючи адміністраторів та звичайних користувачів."""

    strings = {
        "name": "ChatActivity",
        "searching": (
            "<emoji document_id=5188311512791393083>🔎</emoji> <b>Шукаю найбільш активних"
            " користувачів у чаті (спамерів)...\nЦе може зайняти трохи часу.</b>"
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
    }

    async def get_active_participants(self, client: Client, chat_id):
        """Отримуємо всіх активних учасників чату за допомогою Pyrogram."""
        active_users = {}
        async for member in client.get_chat_members(chat_id):
            if not member.user.is_bot:
                active_users[member.user.id] = member.user
        return active_users

    async def get_admin_status(self, client: Client, chat_id, user_id):
        """Перевіряємо, чи є користувач адміністратором."""
        try:
            member = await client.get_chat_member(chat_id, user_id)
            if member.status in ("administrator", "creator"):
                if member.can_restrict_members or member.can_promote_members:
                    return "senior"  
                else:
                    return "junior"  
        except Exception:
            return None  

    async def count_messages(self, client: Client, chat_id, active_users, limit=None):
        """Перевіряємо кількість повідомлень від активних користувачів за допомогою Pyrogram."""
        user_message_count = {}
        async for msg in client.get_chat_history(chat_id, limit=limit):
            user_id = msg.from_user.id if msg.from_user else None
            if user_id and user_id in active_users:
                user_message_count[user_id] = user_message_count.get(user_id, 0) + 1
        return user_message_count

    async def activchat(self, client: Client, message: Message):
        """[кількість] [-m <int>] - Знаходить топ-40 спамерів у чаті."""
        args = utils.get_args_raw(message)
        limit = None

        if "-m" in args:
            limit = int("".join([lim for lim in args[args.find("-m") + 2:] if lim.isdigit()]))
            args = args[: args.find("-m")].strip()

        quantity = int(args) if args.isdigit() else 40  

        message = await message.reply(self.strings["searching"])

        start_time = time.perf_counter()

        chat_id = message.chat.id
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
                admins_senior.append(self.strings["admin_senior"].format(i + 1, user.mention, user.first_name, count))
            elif admin_status == "junior":
                admins_junior.append(self.strings["admin_junior"].format(i + 1, user.mention, user.first_name, count))
            else:
                regular_users.append(self.strings["regular"].format(i + 1, user.mention, user.first_name, count))

        admins_column = "\n".join(admins_senior + admins_junior) if (admins_senior or admins_junior) else "Немає адміністраторів"
        regular_column = "\n".join(regular_users) if regular_users else "Немає звичайних користувачів"

        await message.reply(
            self.strings["active"].format(
                admins_column, regular_column, round(time.perf_counter() - start_time, 2)
            )
        )
