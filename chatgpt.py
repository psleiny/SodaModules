# meta developer: @SodaModules

__version__ = (1, 0, 0)

import contextlib
import logging
import re
import requests
from telethon.tl.types import Message
from .. import loader, utils

logger = logging.getLogger(__name__)

@loader.tds
class ChatGPT(loader.Module):
    """ChatGPT AI API interaction"""

    strings = {
        "name": "ChatGPT",
        "no_args": (
            "<emoji document_id=5240241223632954241>🚫</emoji> <b>No arguments"
            " provided</b>"
        ),
        "question": (
            "<emoji document_id=5974038293120027938>👤</emoji> <b>Question:</b>"
            " {question}\n"
        ),
        "answer": (
            "<emoji document_id=5337109950386683069>🧠</emoji> <b>Answer:</b> {answer}"
        ),
        "loading": "<code>Loading...</code>",
        "no_api_key": (
            "<b>🚫 No API key provided</b>\n<i><emoji"
            " document_id=5199682846729449178>ℹ️</emoji> Get it from the official OpenAI"
            " website and add it to config</i>"
        ),
    }

    strings_ua = {
        "no_args": (
            "<emoji document_id=5240241223632954241>🚫</emoji> <b>Не вказані"
            " аргументи</b>"
        ),
        "question": (
            "<emoji document_id=5974038293120027938>👤</emoji> <b>Питання:</b>"
            " {question}\n"
        ),
        "answer": (
            "<emoji document_id=5337109950386683069>🧠</emoji> <b>Відповідь:</b> {answer}"
        ),
        "loading": "<code>Завантаження...</code>",
        "no_api_key": (
            "<b>🚫 Не вказан API ключ</b>\n<i><emoji"
            " document_id=5199682846729449178>ℹ️</emoji> Отримайте його на офіційному"
            " сайті OpenAI та додайте у конфіг</i>"
        ),
    }

    strings_es = {
        "no_args": (
            "<emoji document_id=5240241223632954241>🚫</emoji> <b>No se han"
            " proporcionado argumentos</b>"
        ),
        "question": (
            "<emoji document_id=5974038293120027938>👤</emoji> <b>Pregunta:</b>"
            " {question}\n"
        ),
        "answer": (
            "<emoji document_id=5337109950386683069>🧠</emoji> <b>Respuesta:</b>"
            " {answer}"
        ),
        "loading": "<code>Cargando...</code>",
        "no_api_key": (
            "<b>🚫 No se ha proporcionado una clave API</b>\n<i><emoji"
            " document_id=5199682846729449178>ℹ️</emoji> Obtenga una en el sitio web"
            " oficial de OpenAI y agréguela a la configuración</i>"
        ),
    }

    # ... (similar strings for other languages)

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "api_key",
                "",
                "API key from OpenAI",
                validator=loader.validators.Hidden(loader.validators.String()),
            ),
        )

    async def _make_request(
        self,
        method: str,
        url: str,
        headers: dict,
        data: dict,
    ) -> dict:
        resp = await utils.run_sync(
            requests.request,
            method,
            url,
            headers=headers,
            json=data,
        )
        return resp.json()

    def _process_code_tags(self, text: str) -> str:
        return re.sub(
            r"`(.*?)`",
            r"<code>\1</code>",
            re.sub(r"```(.*?)```", r"<code>\1</code>", text, flags=re.DOTALL),
            flags=re.DOTALL,
        )

    async def _get_chat_completion(self, prompt: str) -> str:
        resp = await self._make_request(
            method="POST",
            url="https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f'Bearer {self.config["api_key"]}',
            },
            data={
                "model": "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        if resp.get("error", None):
            return f"🚫 {resp['error']['message']}"
        return resp["choices"][0]["message"]["content"]

    @loader.command(
        ua_doc="<питання> - задати питання",
        it_doc="<domanda> - Fai una domanda",
        fr_doc="<question> - Posez une question",
        de_doc="<frage> - Stelle eine Frage",
        es_doc="<pregunta> - Haz una pregunta",
        tr_doc="<soru> - Soru sor",
        uz_doc="<savol> - Savol ber",
    )
    async def gpt(self, message: Message):
        """<question> - Ask a question"""
        if self.config["api_key"] == "":
            return await utils.answer(message, self.strings("no_api_key"))

        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, self.strings("no_args"))

        original_message = await utils.answer(
            message,
            "\n".join(
                [
                    self.strings("question").format(question=args),
                    self.strings("answer").format(answer=self.strings("loading")),
                ]
            ),
        )

        answer = await self._get_chat_completion(args)

        # Edit the original message with the new content
        await original_message.edit(
            "\n".join(
                [
                    self.strings("question").format(question=args),
                    self.strings("answer").format(
                        answer=self._process_code_tags(answer)
                    ),
                ]
            )
        )
