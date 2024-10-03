# meta developer: @SodaModules

import datetime
import logging
import time
from telethon import types

from .. import loader, utils

logger = logging.getLogger(__name__)

@loader.tds
class AFKMod(loader.Module):
    """Повідомляє інших, що ви перебуваєте в AFK і дозволяє додавати та зберігати до 5 медіа."""

    strings = {
        "name": "AFK",
        "gone": "<b>Я перейшов у режим AFK</b>",
        "back": "<b>Я більше не в режимі AFK</b>",
        "afk": "<b>Я зараз в AFK (з {} тому).</b>",
        "afk_reason": "<b>Я зараз в AFK (з {} тому).\nПричина:</b> <i>{}</i>",
        "media_installed": "<b>Медіа AFK було встановлено!</b>",
        "media_saved": "<b>Медіа AFK збережено!</b>",
        "media_removed": "<b>Медіа AFK було видалено.</b>",
        "media_limit_reached": "<b>Досягнуто ліміт збережених медіа (5). Видаліть одне, щоб додати нове.</b>",
        "media_not_found": "<b>Невірний медіа URL або індекс.</b>",
        "media_list": "<b>Збережені медіа:</b>\n\n{}",
        "afk_preview": "<b>Ось як виглядатиме ваше повідомлення AFK:</b>\n\n{}",
        "afk_no_media": "<b>У вас немає збережених медіа.</b>",
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
        self._db.set(__name__, "ratelimit", [])

        await self.allmodules.log("afk", data=args or None)
        await utils.answer(message, self.strings("gone", message))

    async def unafkcmd(self, message):
        """Знімає статус AFK"""
        self._db.set(__name__, "afk", False)
        self._db.set(__name__, "gone", None)
        self._db.set(__name__, "ratelimit", [])
        self._db.set(__name__, "afk_media", None)

        await self.allmodules.log("unafk")
        await utils.answer(message, self.strings("back", message))

    async def afkmediacmd(self, message):
        """.afkmedia <media URL> - Встановити або зберегти медіа для AFK через URL"""
        args = utils.get_args_raw(message)

        if not args or not (args.startswith("http://") or args.startswith("https://")):
            await utils.answer(message, self.strings("media_not_found", message))
            return

        saved_media = self._db.get(__name__, "saved_media", [])

        if len(saved_media) >= 5:
            await utils.answer(message, self.strings("media_limit_reached", message))
            return

        saved_media.append(args)
        self._db.set(__name__, "saved_media", saved_media)
        await utils.answer(message, self.strings("media_saved", message))

    async def setafkmediacmd(self, message):
        """.setafkmedia <index> - Встановити медіа для AFK за індексом збереженого списку"""
        args = utils.get_args_raw(message)

        if not args.isdigit():
            await utils.answer(message, self.strings("media_not_found", message))
            return

        index = int(args) - 1
        saved_media = self._db.get(__name__, "saved_media", [])

        if index < 0 or index >= len(saved_media):
            await utils.answer(message, self.strings("media_not_found", message))
            return

        self._db.set(__name__, "afk_media", saved_media[index])
        await utils.answer(message, self.strings("media_installed", message))

    async def listafkmediacmd(self, message):
        """.listafkmedia - Показати список збережених медіа"""
        saved_media = self._db.get(__name__, "saved_media", [])

        if not saved_media:
            await utils.answer(message, self.strings("afk_no_media", message))
            return

        media_list = "\n".join([f"{i+1}. {url}" for i, url in enumerate(saved_media)])
        await utils.answer(message, self.strings("media_list", message).format(media_list))

    async def removeafkmediacmd(self, message):
        """.removeafkmedia <index> - Видалити медіа з збереженого списку за індексом"""
        args = utils.get_args_raw(message)

        if not args.isdigit():
            await utils.answer(message, self.strings("media_not_found", message))
            return

        index = int(args) - 1
        saved_media = self._db.get(__name__, "saved_media", [])

        if index < 0 or index >= len(saved_media):
            await utils.answer(message, self.strings("media_not_found", message))
            return

        del saved_media[index]
        self._db.set(__name__, "saved_media", saved_media)
        await utils.answer(message, self.strings("media_removed", message))

    async def watcher(self, message):
        if not isinstance(message, types.Message):
            return

        if message.mentioned or getattr(message.to_id, "user_id", None) == self._me.id:
            afk_state = self.get_afk()
            if not afk_state:
                return

            logger.debug("Вас позначили під час AFK")
            ratelimit = self._db.get(__name__, "ratelimit", [])
            if utils.get_chat_id(message) in ratelimit:
                return
            else:
                self._db.setdefault(__name__, {}).setdefault("ratelimit", []).append(
                    utils.get_chat_id(message)
                )
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
            await message.reply(self.strings("afk_preview", message).format(ret), file=media)  
        else:
            await utils.answer(message, self.strings("afk_preview", message).format(ret))

    def get_afk(self):
        return self._db.get(__name__, "afk", False)
