from .. import loader, utils
import re

@loader.tds
class LinkBlocker(loader.Module):
    """Модуль для блокировки сообщений с ссылками и инлайн-кнопками от определенных пользователей"""
    strings = {"name": "LinkBlocker"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            "whitelist_chats", [], "Список ID чатів у вайт-листі"
        )

    @loader.command()
    async def wlchat(self, message):
        """Додає або видаляє поточний чат з вайт-листа"""
        chat_id = str(message.chat_id)
        whitelist_chats = self.config.get("whitelist_chats", [])

        # Преобразуем строку в список, если это строка
        if isinstance(whitelist_chats, str):
            try:
                whitelist_chats = eval(whitelist_chats) if whitelist_chats else []
            except (SyntaxError, NameError):
                whitelist_chats = []

        if not isinstance(whitelist_chats, list):
            whitelist_chats = []

        # Добавление или удаление чата из вайт-листа
        if chat_id in whitelist_chats:
            whitelist_chats.remove(chat_id)
            action = "видалено з"
        else:
            whitelist_chats.append(chat_id)
            action = "додано до"

        # Обновление конфигурации
        self.config["whitelist_chats"] = whitelist_chats

        await message.edit(f"<b>Чат {action} вайт-листа:</b> <code>{chat_id}</code>")

    async def watcher(self, message):
        """Отслеживание и удаление сообщений с ссылками или инлайн-кнопками"""
        # Список ID пользователей, от которых будут удаляться сообщения
        blocked_users = {1961946938, 1624990893, 1994984435, 1961679454, 1718982458}
        chat_id = str(message.chat_id)
        whitelist_chats = self.config.get("whitelist_chats", [])

        # Преобразуем строку в список, если это строка
        if isinstance(whitelist_chats, str):
            try:
                whitelist_chats = eval(whitelist_chats) if whitelist_chats else []
            except (SyntaxError, NameError):
                whitelist_chats = []

        if not isinstance(whitelist_chats, list):
            whitelist_chats = []

        # Если чат в вайт-листе, игнорируем его сообщения
        if chat_id in whitelist_chats:
            return
        
        # Проверяем, является ли отправитель заблокированным пользователем
        if message.sender_id in blocked_users:
            # Проверка на наличие ссылки
            if re.search(r'http[s]?://', message.raw_text):
                await message.delete()
                return
            
            # Проверка на наличие инлайн-кнопок
            if message.reply_markup is not None:
                await message.delete()
                return
