# meta developer: @SodaModules

import datetime
import logging
import time
from telethon import types

from .. import loader, utils

logger = logging.getLogger(__name__)

@loader.tds
class AFKMod(loader.Module):
    """Повідомляє інших, що ви перебуваєте в AFK і дозволяє додавати медіа через URL."""

    strings = {
        "name": "afk_with_gif",
        "gone": "<b>Я перейшов у режим AFK</b>",
        "back": "<b>Я більше не в режимі AFK</b>",
        "afk": "<b>Я зараз в AFK (з {} тому).</b>",
        "afk_reason": "<b>Я зараз в AFK (з {} тому).\nПричина:</b> <i>{}</i>",
        "media_installed": "<b>Медіа AFK було встановлено!</b>",
        "media_removed": "<b>Медіа AFK було видалено.</b>",
        "media_not_found": "<b>Невірний медіа URL для AFK.</b>",
        "afk_preview": "<b>Ось як виглядатиме ваше повідомлення AFK:</b>\n\n{}",
    }

    async def client_ready(self, client, db):
        self._db = db
        self._me = await client.get_me()

    async def afkcmd(self, message):
        """.afk [необов'язкова причина]"""
        args = utils.get_args_raw(message)

        if args:
            self._db.set(__name__, "afk", args)
        else:
            self._db.set(__name__, "afk", True)

        self._db.set(__name__, "gone", time.time())
        self._db.set(__name__, "ratelimit", {})  

        await self.allmodules.log("afk", data=args or None)
        await utils.answer(message, self.strings("gone", message))

    async def unafkcmd(self, message):
        """Знімає статус AFK"""
        self._db.set(__name__, "afk", False)
        self._db.set(__name__, "gone", None)
        self._db.set(__name__, "ratelimit", {}) 

        await self.allmodules.log("unafk")
        await utils.answer(message, self.strings("back", message))

    async def afkmediacmd(self, message):
        """.afkmedia <URL медіа> - Встановити або замінити медіа для AFK через URL"""
        args = utils.get_args_raw(message)

        if not args or not (args.startswith("http://") or args.startswith("https://")):
            await utils.answer(message, self.strings("media_not_found", message))
            return

        self._db.set(__name__, "afk_media", args)
        await utils.answer(message, self.strings("media_installed", message))

    async def removeafkmediacmd(self, message):
        """.removeafkmedia - Видалити поточний медіа URL для AFK"""
        self._db.set(__name__, "afk_media", None)
        await utils.answer(message, self.strings("media_removed", message))

    async def watcher(self, message):
        if not isinstance(message, types.Message):
            return

        if message.mentioned or getattr(message.to_id, "user_id", None) == self._me.id:
            afk_state = self.get_afk()
            if not afk_state:
                return

            logger.debug("Вас позначили під час AFK")
            ratelimit = self._db.get(__name__, "ratelimit", {})

            chat_id = utils.get_chat_id(message)
            if ratelimit.get(chat_id):
                return 
            else:
                ratelimit[chat_id] = True
                self._db.set(__name__, "ratelimit", ratelimit)
                self._db.save()

            user = await utils.get_user(message)
            if user.is_self or user.bot or user.verified:
                logger.debug("Користувач - це бот або він підтверджений.")
                return

            now = datetime.datetime.now().replace(microsecond=0)
            gone = datetime.datetime.fromtimestamp(
                self._db.get(__name__, "gone")
            ).replace(microsecond=0)
            diff = now - gone

            if afk_state is True:
                ret = self.strings("afk", message).format(diff)
            elif afk_state is not False:
                ret = self.strings("afk_reason", message).format(diff, afk_state)

            media = self._db.get(__name__, "afk_media")
            if media:
                await message.reply(ret, file=media) 
            else:
                await utils.answer(message, ret, reply_to=message)

    async def afkpreviewcmd(self, message):
        """.afkpreview - Попередній перегляд вашого поточного AFK повідомлення"""
        afk_state = self.get_afk()
        if not afk_state:
            await utils.answer(message, "<b>Ви наразі не перебуваєте в режимі AFK.</b>")
            return

        now = datetime.datetime.now().replace(microsecond=0)
        gone = datetime.datetime.fromtimestamp(self._db.get(__name__, "gone")).replace(microsecond=0)
        diff = now - gone

        if afk_state is True:
            ret = self.strings("afk", message).format(diff)
        elif afk_state is not False:
            ret = self.strings("afk_reason", message).format(diff, afk_state)

        media = self._db.get(__name__, "afk_media")
        if media:
            await message.reply(self.strings("afk_preview", message).format(ret), file=media)  # Надсилаємо медіа безпосередньо
        else:
            await utils.answer(message, self.strings("afk_preview", message).format(ret))

    def get_afk(self):
        return self._db.get(__name__, "afk", False)
