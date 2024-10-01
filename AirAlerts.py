import logging
from asyncio import sleep
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import Message
from telethon.utils import get_display_name
from .. import loader, utils
from ..inline import GeekInlineQuery, rand

logger = logging.getLogger(__name__)

ua = [
    "Вінницька область", "Волинська область", "Дніпропетровська область", 
    "Донецька область", "Житомирська область", "Закарпатська область", 
    "Запорізька область", "Івано-Франківська область", "Київська область", 
    "Кіровоградська область", "Луганська область", "Львівська область", 
    "Миколаївська область", "Одеська область", "Полтавська область", 
    "Рівненська область", "Сумська область", "Тернопільська область", 
    "Харківська область", "Херсонська область", "Хмельницька область", 
    "Черкаська область", "Чернівецька область", "Чернігівська область", 
    "місто Київ", "місто Севастополь"
]

class AirAlertMod(loader.Module):
    """🇺🇦 Предупреждение о воздушной тревоге.
    Нужно быть подписаным на @air_alert_ua и включены уведомления в вашем боте"""

    strings = {"name": "AirAlert"}

    async def client_ready(self, client, db) -> None:
        self.regions = db.get(self.strings["name"], "regions", [])
        self.nametag = db.get(self.strings["name"], "nametag", "")
        self.forwards = db.get(self.strings["name"], "forwards", [])

        self.db = db
        self.client = client
        self.bot_id = (await self.inline.bot.get_me()).id
        self.me = (await client.get_me()).id

        try:
            await client(JoinChannelRequest(await self.client.get_entity("t.me/air_alert_ua")))
        except Exception:
            logger.error("Can't join t.me/air_alert_ua")

    async def alertforwardcmd(self, message: Message) -> None:
        """Перенаправление предупреждений в другие чаты.
        Для добавления/удаления введите команду с ссылкой на чат.
        Для просмотра чатов введите команду без аргументов.
        Для установки кастомной таблички введите .alertforward set <text>"""
        text = utils.get_args_raw(message)

        if text[:3] == "set":
            self.nametag = text[4:]
            self.db.set(self.strings["name"], "nametag", self.nametag)
            return await utils.answer(
                message,
                f"🏷 <b>Табличка успешно установлена: <code>{self.nametag}</code></b>",
            )

        if not text:
            chats = "<b>Текущие чаты для перенаправления:</b>\n"
            for chat in self.forwards:
                chats += f"{get_display_name(await self.client.get_entity(chat))}\n"
            await utils.answer(message, chats)
            return

        try:
            chat = (await self.client.get_entity(text.replace("https://", ""))).id
        except Exception:
            await utils.answer(message, "<b>Чат не найден</b>")
            return

        if chat in self.forwards:
            self.forwards.remove(chat)
            self.db.set(self.strings["name"], "forwards", self.forwards)
            await utils.answer(message, "<b>Чат успешно удален для перенаправления</b>")
        else:
            self.forwards.append(chat)
            self.db.set(self.strings["name"], "forwards", self.forwards)
            await utils.answer(message, "<b>Чат успешно установлен для перенаправления</b>")

    async def alert_inline_handler(self, query: GeekInlineQuery) -> None:
        """Выбор регионов.
        Чтобы получать все предупреждения введите alert all.
        Чтобы посмотреть ваши регионы alert my"""
        text = query.args

        if not text:
            result = ua
        elif text == "my":
            result = self.regions
        else:
            result = [region for region in ua if text.lower() in region.lower()]

        if not result:
            await query.e404()
            return

        res = [
            InlineQueryResultArticle(
                id=rand(20),
                title=f"{'✅' if reg in self.regions else '❌'}{reg if reg != 'all' else 'Всі сповіщення'}",
                description=(
                    f"Нажмите чтобы {'удалить' if reg in self.regions else 'добавить'}"
                    if reg != "all"
                    else (
                        "🇺🇦 Нажмите чтобы"
                        f" {'выключить' if 'all' in self.regions else 'включить'} всі"
                        " сповіщення"
                    )
                ),
                input_message_content=InputTextMessageContent(
                    f"⌛ Редагування регіону <code>{reg}</code>",
                    parse_mode="HTML",
                ),
            )
            for reg in result[:50]
        ]
        await query.answer(res, cache_time=0)

    async def watcher(self, message: Message) -> None:
        """Forward air alert messages to configured chats."""
        if (
            getattr(message, "out", False)
            and getattr(message, "via_bot_id", False)
            and message.via_bot_id == self.bot_id
            and "⌛ Редагування регіону" in getattr(message, "raw_text", "")
        ):
            self.regions = self.db.get(self.strings["name"], "regions", [])
            region = message.raw_text[25:]
            state = "доданий"
            if region not in self.regions:
                self.regions.append(region)
            else:
                self.regions.remove(region)
                state = "видалений"
            self.db.set(self.strings["name"], "regions", self.regions)
            
            try:
                e = await self.client.get_entity("t.me/air_alert_ua")
                sub = not e.left
            except Exception:
                sub = False
            
            n = "\n"
            res = f"<b>Регіон <code>{region}</code> успішно {state}</b>{n}"
            if not sub:
                res += "<b>НЕ ВИХОДЬ З @air_alert_ua (інакше нічого не працюватиме)</b>"
                await self.client(
                    JoinChannelRequest(
                        await self.client.get_entity("t.me/air_alert_ua")
                    )
                )
            await self.inline.form(res, message=message)
        
        if (
            getattr(message, "peer_id", False)
            and getattr(message.peer_id, "channel_id", 0) == 1766138888
            and ("all" in self.regions or any(reg in message.raw_text for reg in self.regions))
        ):
            await self.inline.bot.send_message(self.me, message.text, parse_mode="HTML")
            for chat in self.forwards:
                await self.client.send_message(chat, message.text + "\n\n" + self.nametag)
