import random
from telethon import types
from .. import loader, utils

@loader.tds
class MegaMozgMod(loader.Module):
    strings = {
        "name": "MegaMozg",
        "pref": "<b>[MegaMozg]</b> ",
        "need_arg": "{}Потрібен аргумент",
        "status": "{}{}",
        "on": "{}Ввімкнено",
        "off": "{}Вимкнено",
    }
    _db_name = "MegaMozg"

    async def client_ready(self, _, db):
        self.db = db

    @staticmethod
    def str2bool(v: str) -> bool:
        """
        Converts a string to a boolean.
        Supports various representations of truthy and falsy values.
        """
        return v.lower() in (
            "yes", "y", "ye", "true", "t", "1", "on", "enable", "start", "run", "go", "да",
        )

    async def mozgcmd(self, m: types.Message):
        ".mozg <on/off/...> - Переключити режим дурника в чаті"
        args = utils.get_args_raw(m)
        if not m.chat:
            return
        
        chat = m.chat.id
        chats = set(self.db.get(self._db_name, "chats", []))

        if not args:
            # Handle missing argument
            return await utils.answer(m, self.strings("need_arg").format(self.strings("pref")))

        if self.str2bool(args):
            chats.add(chat)
            self.db.set(self._db_name, "chats", list(chats))
            return await utils.answer(m, self.strings("on").format(self.strings("pref")))
        
        chats.discard(chat)
        self.db.set(self._db_name, "chats", list(chats))
        return await utils.answer(m, self.strings("off").format(self.strings("pref")))

    async def mozgchancecmd(self, m: types.Message):
        ".mozgchance <int> - Встановити шанс 1 до N.\n0 - завжди відповідати"
        args = utils.get_args_raw(m)
        if not args or not args.isdigit():
            # Handle missing or invalid argument
            return await utils.answer(m, self.strings("need_arg").format(self.strings("pref")))

        chance = int(args)
        self.db.set(self._db_name, "chance", chance)
        return await utils.answer(m, self.strings("status").format(self.strings("pref"), chance))

    async def watcher(self, m: types.Message):
        """
        Watches the chat for random replies based on a set chance and random words.
        """
        # Preliminary checks
        if not isinstance(m, types.Message):
            return
        if m.sender_id == (await m.client.get_me()).id or not m.chat:
            return

        chat_id = m.chat.id
        active_chats = self.db.get(self._db_name, "chats", [])
        if chat_id not in active_chats:
            return
        
        # Check random chance logic
        chance = self.db.get(self._db_name, "chance", 0)
        if chance > 0 and random.randint(0, chance) != 0:
            return

        # Randomly select words from the message
        text = m.raw_text
        words = list(filter(lambda x: len(x) >= 3, text.split()))
        if len(words) < 2:
            return

        selected_words = random.sample(words, 2)
        messages = []

        # Search for messages containing the random words
        for word in selected_words:
            async for msg in m.client.iter_messages(m.chat.id, search=word):
                if msg.replies and msg.replies.max_id:
                    messages.append(msg)

        if not messages:
            return

        # Select a random message to reply to
        chosen_msg = random.choice(messages)
        sid = chosen_msg.id
        eid = chosen_msg.replies.max_id

        # Get messages in the reply thread
        reply_msgs = [
            msg async for msg in m.client.iter_messages(m.chat.id, ids=list(range(sid + 1, eid + 1)))
            if msg and msg.reply_to and msg.reply_to.reply_to_msg_id == sid
        ]

        if reply_msgs:
            reply_msg = random.choice(reply_msgs)
            await m.reply(reply_msg)
