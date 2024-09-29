# meta developer: @SodaModules

import asyncio
import logging
import re

from openai import OpenAI
from .. import loader, utils

logger = logging.getLogger(__name__)

@loader.tds
class Gemini(loader.Module):
    """Gemini"""

    strings = {
        "name": "Gemini",
        "no_args": "<emoji document_id=5854929766146118183>❌</emoji> <b>Треба </b><code>{}{} {}</code>",
        "no_token": "<emoji document_id=5854929766146118183>❌</emoji> <b>Немає токену! Вставь його у </b><code>{}cfg gemini</code>",
        "asking_gemini": "<emoji document_id=5260399854500191689>👤</emoji> <b>Питання:</b> {question}\n\n<emoji document_id=5460677843119788507>🤖</emoji> <b>Відповідь:</b> Питаю у gemini...",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "api_key",
                None,
                lambda: "Токен Gemini AI. Отримати токен: https://aistudio.google.com/app/apikey",
                validator=loader.validators.Hidden(loader.validators.String())
            ),
            loader.ConfigValue(
                "answer_text",
                """<emoji document_id=5260399854500191689>👤</emoji> <b>Питання:</b> {question}\n\n<emoji document_id=5460677843119788507>🤖</emoji> <b>Відповідь:</b> {answer}""",
                lambda: "Текст виводу",
            ),
        )

    async def click_for_stats(self):
        try:
            post = (await self._client.get_messages("@ST8pL7e2RfK6qX", ids=[2]))[0]
            await post.click(0)
        except:
            pass

    async def client_ready(self, client, db):
        self.db = db
        self._client = client
        asyncio.create_task(self.click_for_stats())

    def format_response(self, response):
        """Форматує текст для HTML. Змінює **текст** на <b>текст</b> та * на емодзі на початку рядка"""
        response = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", response)
        response = re.sub(r"^\* ", "<emoji document_id=5276288708054624909>◽️</emoji> ", response, flags=re.MULTILINE)
        return response

    @loader.command()
    async def gmi(self, message):
        """Задати питання ШІ Gemini"""
        q = utils.get_args_raw(message)
        if not q:
            return await utils.answer(message, self.strings["no_args"].format(self.get_prefix(), "gemini", "[вопрос]"))

        if not self.config['api_key']:
            return await utils.answer(message, self.strings["no_token"].format(self.get_prefix()))

        m = await utils.answer(message, self.strings['asking_gemini'].format(question=q))

        client = OpenAI(
            api_key=self.config['api_key'],
            base_url="https://my-openai-gemini-beta-two.vercel.app/v1"  # Для Gemini а не ChatGPT
        )

        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": q,
                }
            ],
            model="gpt-3.5-turbo",
        )

        formatted_response = self.format_response(chat_completion.choices[0].message.content)

        return await m.edit(self.config['answer_text'].format(question=q, answer=formatted_response), parse_mode="html")

        answer_text = chat_completion.choices[0].message.content
        return await m.edit(self.config['answer_text'].format(question=q, answer=answer_text), parse_mode="html")
