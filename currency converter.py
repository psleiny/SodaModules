# meta developer @lir1mod

import aiohttp
from hikka import loader, utils
from telethon.tl.patched import Message
import logging

logger = logging.getLogger(__name__)

@loader.tds
class CurrencyConverterMod(loader.Module):
    """Конвертер валют"""

    strings = {
        "name": "Конвертер Валют",
        "fetching": "💱 <b>Отримуємо курс обміну...</b>",
        "invalid_format": "❌ <b>Неправильний формат! Використовуйте:</b> <code>.convert &lt;сума&gt; &lt;валюта_з&gt; to &lt;валюта_в&gt;</code>",
        "conversion_result": "💱 <b>{amount} {from_currency} = {converted} {to_currency}</b>",
        "error": "⚠️ <b>Не вдалося отримати курс обміну. Спробуйте пізніше.</b>",
        "currencies_list": "💱 <b>Доступні валюти та їх скорочення:</b>\n\n{}",
    }

    api_url = "https://api.exchangerate-api.com/v4/latest/{}"

    @loader.command("convert", prefixes=".")
    async def convert_cmd(self, m: Message):
        """Конвертувати між валютами: .convert <сума> <валюта_з> to <валюта_в>"""
        args = utils.get_args_raw(m).strip().split()

        if len(args) != 4 or args[2].lower() != "to":
            return await utils.answer(m, self.strings["invalid_format"])

        try:
            amount = float(args[0])
            from_currency = args[1].upper()
            to_currency = args[3].upper()

            await utils.answer(m, self.strings["fetching"])

            exchange_rate = await self.fetch_exchange_rate(from_currency)

            if to_currency not in exchange_rate["rates"]:
                return await utils.answer(m, f"❌ <b>Непідтримувана валюта: {to_currency}</b>")

            conversion_rate = exchange_rate["rates"][to_currency]
            converted_amount = round(amount * conversion_rate, 2)

            await utils.answer(m, self.strings["conversion_result"].format(
                amount=amount, from_currency=from_currency, converted=converted_amount, to_currency=to_currency
            ))

        except Exception as e:
            logger.error(f"Помилка при конвертації валюти: {e}")
            await utils.answer(m, self.strings["error"])

    async def fetch_exchange_rate(self, base_currency):
        """Отримання курсів обміну для даної базової валюти."""
        async with aiohttp.ClientSession() as session:
            async with session.get(self.api_url.format(base_currency)) as resp:
                if resp.status != 200:
                    raise aiohttp.ClientError("Не вдалося отримати курс обміну.")
                return await resp.json()

    @loader.command("currencies", prefixes=".")
    async def currencies_cmd(self, m: Message):
        """Показати список доступних валют та їх скорочень."""
        currency_list = "\n".join([f"{name}: {abbr}" for name, abbr in self.currencies.items()])
        await utils.answer(m, self.strings["currencies_list"].format(currency_list))

    def __init__(self):
        pass

    currencies = {
        "Австралійський долар": "AUD",
        "Австрійський шилінг": "ATS",
        "Білоруський рубль": "BYN",
        "Бельгійський франк": "BEF",
        "Болгарський лев": "BGN",
        "Бразильський реал": "BRL",
        "Британський фунт стерлінгів": "GBP",
        "Угорський форинт": "HUF",
        "Венесуельський болівар": "VEB",
        "В'єтнамський донг": "VND",
        "Гонконзький долар": "HKD",
        "Грецька драхма": "GRD",
        "Датська крона": "DKK",
        "Євро": "EUR",
        "Індійська рупія": "INR",
        "Індонезійська рупія": "IDR",
        "Ірландський фунт": "IEP",
        "Іспанська песета": "ESP",
        "Італійська ліра": "ITL",
        "Єменський ріал": "YER",
        "Казахстанський тенге": "KZT",
        "Канадський долар": "CAD",
        "Китайський юань": "CNY",
        "Кіпрський фунт": "CYP",
        "Латвійський лат": "LVL",
        "Литовський літ": "LTL",
        "Малайзійський ринггіт": "MYR",
        "Мексиканське песо": "MXN",
        "Молдовський лей": "MDL",
        "Німецька марка": "DEM",
        "Нідерландський гульден": "NLG",
        "Норвезька крона": "NOK",
        "Новозеландський долар": "NZD",
        "Пакистанська рупія": "PKR",
        "Польський злотий": "PLN",
        "Португальський ескудо": "PTE",
        "Російський рубль": "RUB",
        "Румунський лей": "RON",
        "Саудівський ріал": "SAR",
        "Сінгапурський долар": "SGD",
        "Словацька крона": "SKK",
        "Словенський толар": "SIT",
        "Тайванський долар": "TWD",
        "Тайський бат": "THB",
        "Турецька ліра": "TRY",
        "Українська гривня": "UAH",
        "Філіппінське песо": "PHP",
        "Фінська марка": "FIM",
        "Французький франк": "FRF",
        "Хорватська куна": "HRK",
        "Чеська крона": "CZK",
        "Чилійське песо": "CLP",
        "Швейцарський франк": "CHF",
        "Шведська крона": "SEK",
        "Еміратський дирхам": "AED",
        "Естонська крона": "EEK",
        "Південноафриканський ренд": "ZAR",
        "Південнокорейський вон": "KRW",
        "Японська єна": "JPY",
    }
