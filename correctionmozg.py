import random
from telethon import types
from telethon.tl.custom.message import Message
from .. import loader, utils

@loader.tds
class MegaMozgMod(loader.Module):
    """
    Module to toggle a mode in chats that allows random replies based on certain conditions.
    """
    strings = {
        "name": "MegaMozg",
        "pref": "<b>[MegaMozg]</b> ",
        "need_arg": "{}Потрібен аргумент",
        "status": "{}Шанс встановлено на {}",
        "on": "{}Ввімкнено",
        "off": "{}Вимкнено",
    }

    _db_name = "MegaMozg"
    _default_chance = 0

    async def client_ready(self, client, db):
        self.db = db

    @staticmethod
    def str2bool(value: str) -> bool:
        """
        Converts a string to a boolean value. Supports various representations
        of truthy and falsy strings.
        """
        truthy_values = {"yes", "y", "ye", "true", "t", "1", "on", "enable", "start", "run", "go", "да"}
        return value.strip().lower() in truthy_values

    def get_active_chats(self) -> set:
        """
        Fetches the set of chats where the mode is enabled.
        """
        return set(self.db.get(self._db_name, "chats", []))

    def set_active_chats(self, chats: set):
        """
        Updates the list of active chats in the database.
        """
        self.db.set(self._db_name, "chats", list(chats))

    def get_reply_chance(self) -> int:
        """
        Retrieves the current reply chance from the database. Defaults to 0 if not set.
        """
        return self.db.get(self._db_name, "chance", self._default_chance)

    def set_reply_chance(self, chance: int):
        """
        Sets the reply chance in the database.
        """
        self.db.set(self._db_name, "chance", chance)

    async def mozgcmd(self, message: Message):
        """
        .mozg <on/off> - Toggle the MegaMozg mode in the chat.
        """
        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, self.strings["need_arg"].format(self.strings["pref"]))

        chat_id = message.chat_id
        if not chat_id:
            return

        active_chats = self.get_active_chats()
        if self.str2bool(args):
            active_chats.add(chat_id)
            self.set_active_chats(active_chats)
            return await utils.answer(message, self.strings["on"].format(self.strings["pref"]))
        
        active_chats.discard(chat_id)
        self.set_active_chats(active_chats)
        return await utils.answer(message, self.strings["off"].format(self.strings["pref"]))

    async def mozgchancecmd(self, message: Message):
        """
        .mozgchance <int> - Set the reply chance as 1 out of N.
        0 means always respond.
        """
        args = utils.get_args_raw(message)
        if not args or not args.isdigit():
            return await utils.answer(message, self.strings["need_arg"].format(self.strings["pref"]))

        chance = int(args)
        self.set_reply_chance(chance)
        return await utils.answer(message, self.strings["status"].format(self.strings["pref"], chance))

    async def watcher(self, message: Message):
        """
        Watches the chat for messages and replies based on a set chance and random word matching.
        """
        if not isinstance(message, types.Message):
            return
        if message.sender_id == (await message.client.get_me()).id or not message.chat_id:
            return

        chat_id = message.chat_id
        active_chats = self.get_active_chats()
        if chat_id not in active_chats:
            return

        if not self.should_reply():
            return

        selected_words = self.extract_random_words(message.raw_text, 2)
        if not selected_words:
            return

        messages = await self.search_for_messages(message, selected_words)
        if not messages:
            return

        await self.reply_to_random_message(message, messages)

    def should_reply(self) -> bool:
        """
        Determines if the bot should reply based on the set chance.
        """
        chance = self.get_reply_chance()
        return chance == 0 or random.randint(0, chance) == 0

    def extract_random_words(self, text: str, count: int) -> list:
        """
        Extracts random words from a given text, filtering by word length (>= 3).
        """
        words = list(filter(lambda x: len(x) >= 3, text.split()))
        return random.sample(words, count) if len(words) >= count else []

    async def search_for_messages(self, message: Message, words: list) -> list:
        """
        Searches the chat for messages that contain any of the given words.
        """
        found_messages = []
        for word in words:
            async for msg in message.client.iter_messages(message.chat_id, search=word):
                if msg.replies and msg.replies.max_id:
                    found_messages.append(msg)
        return found_messages

    async def reply_to_random_message(self, message: Message, messages: list):
        """
        Selects a random message from the list and replies to a random message in its reply thread.
        """
        chosen_msg = random.choice(messages)
        start_id = chosen_msg.id
        end_id = chosen_msg.replies.max_id

        reply_msgs = [
            msg async for msg in message.client.iter_messages(message.chat_id, ids=list(range(start_id + 1, end_id + 1)))
            if msg and msg.reply_to and msg.reply_to.reply_to_msg_id == start_id
        ]

        if reply_msgs:
            reply_msg = random.choice(reply_msgs)
            await message.reply(reply_msg)
