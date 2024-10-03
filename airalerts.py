import logging
from alerts_in_ua import Client as AlertsClient
from telethon.tl.types import Message
from telethon.utils import get_display_name
from .. import loader, utils

logger = logging.getLogger(__name__)

class AirAlertMod(loader.Module):
    """🇺🇦 Air Alert Warning with region selection and API key setup."""

    strings = {"name": "AirAlert"}

    def __init__(self):
        self.regions = []
        self.nametag = ""
        self.forwards = []
        self.api_key = ""
        self.selected_region = ""
        self.bot_id = None
        self.me = None
        self.alerts_client = None

    async def client_ready(self, client, db) -> None:
        """Initialize client and database settings."""
        self.regions = db.get(self.strings["name"], "regions", [])
        self.nametag = db.get(self.strings["name"], "nametag", "")
        self.forwards = db.get(self.strings["name"], "forwards", [])
        self.api_key = db.get(self.strings["name"], "api_key", "")
        self.selected_region = db.get(self.strings["name"], "selected_region", "")
        self.db = db
        self.client = client
        self.bot_id = (await self.inline.bot.get_me()).id
        self.me = (await client.get_me()).id

        if self.api_key:
            self.alerts_client = AlertsClient(token=self.api_key)

    async def setapikeycmd(self, message: Message) -> None:
        """Command to set the API key."""
        api_key = utils.get_args_raw(message)

        if not api_key:
            await utils.answer(message, "<b>Введите ваш API ключ после команды: .setapikey <API_KEY></b>")
            return

        self.api_key = api_key
        self.db.set(self.strings["name"], "api_key", self.api_key)
        self.alerts_client = AlertsClient(token=self.api_key)
        await utils.answer(message, "<b>API ключ успешно установлен!</b>")

    async def setregioncmd(self, message: Message) -> None:
        """Command to select the region for notifications."""
        region = utils.get_args_raw(message)

        if not region:
            await utils.answer(message, "<b>Введите название региона для установки уведомлений.</b>")
            return

        if region not in ua:  # `ua` is the list of Ukrainian regions
            await utils.answer(message, "<b>Неправильный регион. Пожалуйста, выберите корректный регион.</b>")
            return

        self.selected_region = region
        self.db.set(self.strings["name"], "selected_region", self.selected_region)
        await utils.answer(message, f"<b>Регион для уведомлений успешно установлен: <code>{region}</code></b>")

    async def checkalertcmd(self, message: Message) -> None:
        """Command to check the current alert status for the selected region."""
        if not self.api_key:
            await utils.answer(message, "<b>API ключ не установлен. Используйте команду .setapikey.</b>")
            return

        if not self.selected_region:
            await utils.answer(message, "<b>Регион не выбран. Используйте команду .setregion для выбора региона.</b>")
            return

        active_alerts = self.alerts_client.get_air_raid_alert_statuses_by_oblast()

        if not active_alerts:
            await utils.answer(message, "<b>Не удалось получить данные о предупреждениях.</b>")
            return

        relevant_alerts = [alert for alert in active_alerts if alert["region"] == self.selected_region]

        if relevant_alerts:
            await utils.answer(message, f"<b>⚠️ Внимание! В регионе {self.selected_region} сейчас воздушная тревога!</b>")
        else:
            await utils.answer(message, f"<b>✅ В регионе {self.selected_region} нет активных воздушных тревог.</b>")

    async def alertforwardcmd(self, message: Message) -> None:
        """Command for managing forwarding of alerts to other chats."""
        text = utils.get_args_raw(message)
        
        if text[:3] == "set":
            self.nametag = text[4:]
            self.db.set(self.strings["name"], "nametag", self.nametag)
            return await utils.answer(
                message, f"🏷 <b>Табличка успешно установлена: <code>{self.nametag}</code></b>"
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

    async def watcher(self, message: Message) -> None:
        """Fetch and forward air alert messages based on region."""
        if not self.alerts_client:
            logger.error("API client is not set. Use .setapikey to configure.")
            return

        active_alerts = self.alerts_client.get_air_raid_alert_statuses_by_oblast()

        if not active_alerts:
            return

        relevant_alerts = [alert for alert in active_alerts if alert["region"] == self.selected_region]

        if relevant_alerts:
            tasks = [
                self.inline.bot.send_message(self.me, str(relevant_alerts), parse_mode="HTML")
            ]
            for chat in self.forwards:
                tasks.append(
                    self.client.send_message(chat, str(relevant_alerts) + "\n\n" + self.nametag)
                )
            await gather(*tasks)
