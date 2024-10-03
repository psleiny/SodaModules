# meta developer: @SodaModules

from .. import loader, utils
import re

@loader.tds
class LinkBlocker(loader.Module):
    """Модуль для блокировки сообщений с ссылками и инлайн-кнопками от определенных пользователей"""
    strings = {"name": "LinkBlocker"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            "whitelist_chats", [], "Список ID чатів у вайт-листі",
            "blocked_users", [], "Список ID заблокованих користувачів"
        )

    @loader.command()
    async def wlchat(self, message):
        """Додає або видаляє поточний чат з вайт-листа"""
        chat_id = str(message.chat_id)
        whitelist_chats = self.config.get("whitelist_chats", [])

        if isinstance(whitelist_chats, str):
            try:
                whitelist_chats = eval(whitelist_chats) if whitelist_chats else []
            except (SyntaxError, NameError):
                whitelist_chats = []

        if not isinstance(whitelist_chats, list):
            whitelist_chats = []

        if chat_id in whitelist_chats:
            whitelist_chats.remove(chat_id)
            action = "видалено з"
        else:
            whitelist_chats.append(chat_id)
            action = "додано до"

        self.config["whitelist_chats"] = whitelist_chats
        await message.edit(f"<b>Чат {action} вайт-листа:</b> <code>{chat_id}</code>")

    @loader.command()
    async def adduser(self, message):
        """Додає користувача до заблокованого списку"""
        args = utils.get_args_raw(message)
        if not args.isdigit():
            await message.edit("<b>Невірний ID користувача. Будь ласка, введіть коректний ID.</b>")
            return

        user_id = int(args)
        blocked_users = self.config.get("blocked_users", [])

        if user_id in blocked_users:
            await message.edit(f"<b>Користувач вже в заблокованому списку:</b> <code>{user_id}</code>")
        else:
            blocked_users.append(user_id)
            self.config["blocked_users"] = blocked_users
            await message.edit(f"<b>Користувача додано до заблокованого списку:</b> <code>{user_id}</code>")

    @loader.command()
    async def removeuser(self, message):
        """Видаляє користувача із заблокованого списку"""
        args = utils.get_args_raw(message)
        if not args.isdigit():
            await message.edit("<b>Невірний ID користувача. Будь ласка, введіть коректний ID.</b>")
            return

        user_id = int(args)
        blocked_users = self.config.get("blocked_users", [])

        if user_id in blocked_users:
            blocked_users.remove(user_id)
            self.config["blocked_users"] = blocked_users
            await message.edit(f"<b>Користувача видалено із заблокованого списку:</b> <code>{user_id}</code>")
        else:
            await message.edit(f"<b>Користувач не знайдений у заблокованому списку:</b> <code>{user_id}</code>")

    async def watcher(self, message):
        """Отслеживание и удаление сообщений с ссылками или инлайн-кнопками"""
        chat_id = str(message.chat_id)
        whitelist_chats = self.config.get("whitelist_chats", [])
        blocked_users = self.config.get("blocked_users", [])

        if isinstance(whitelist_chats, str):
            try:
                whitelist_chats = eval(whitelist_chats) if whitelist_chats else []
            except (SyntaxError, NameError):
                whitelist_chats = []

        if not isinstance(whitelist_chats, list):
            whitelist_chats = []

        if chat_id in whitelist_chats:
            return

        if message.sender_id in blocked_users:
            if re.search(r'http[s]?://', message.raw_text):
                await message.delete()
                return

            if message.reply_markup is not None:
                await message.delete()
                return
