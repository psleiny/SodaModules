from .. import loader, utils
import asyncio
from typing import List, Optional


def register(cb):
    cb(Spam())


class SpamHandler(loader.Module):
    """Знесення мозку адміна(спам)"""
    strings = {"name": "Spam"}

    def __init__(self):
        self.running = True

    async def spamcmd(self, message):
        """.spam <кількість:int> <текст або відповідь> - Звичайний спам."""
        data = await self._prepare_data(message, require_count=True)
        if not data:
            return await self._show_help(message, "spam")

        count, content = data
        await self._bulk_send(message, content, count)

    async def cspamcmd(self, message):
        """.cspam <текст або відповідь> - Спам символами."""
        data = await self._prepare_data(message)
        if not data:
            return await self._show_help(message, "cspam")

        _, content = data
        await self._bulk_send(message, list(content), len(content))

    async def wspamcmd(self, message):
        """.wspam <текст або відповідь> - Спам словами."""
        data = await self._prepare_data(message)
        if not data:
            return await self._show_help(message, "wspam")

        _, content = data
        words = content.split()
        await self._bulk_send(message, words, len(words))

    async def delayspamcmd(self, message):
        """.delayspam <затримка:float> <кількість:int> <текст або відповідь> - Спам із затримкою."""
        args = utils.get_args_raw(message).split(maxsplit=2)
        if len(args) < 3:
            return await self._show_help(message, "delayspam")

        try:
            delay = float(args[0])
            count = int(args[1])
            content = args[2]
        except ValueError:
            return await self._show_help(message, "delayspam")

        await message.delete()
        for _ in range(count):
            if not self.running:
                break
            await message.respond(content)
            await asyncio.sleep(delay)

    async def reversecmd(self, message):
        """.reverse <текст або відповідь> - Відправляє текст у зворотному порядку."""
        data = await self._prepare_data(message)
        if not data:
            return await self._show_help(message, "reverse")

        _, content = data
        reversed_content = content[::-1]
        await message.respond(reversed_content)

    async def stopspamcmd(self, message):
        """.stopspam - Зупиняє поточний спам."""
        self.running = False
        await message.respond("\u2705 Спам зупинено.")

    async def _prepare_data(self, message, require_count: bool = False) -> Optional[List]:
        args = utils.get_args(message)
        reply = await message.get_reply_message()

        if require_count:
            if len(args) < 2:
                return None

            try:
                count = int(args[0])
                if count <= 0:
                    raise ValueError
            except ValueError:
                return None

            content = " ".join(args[1:]) if not reply else reply.text or ""
            return [count, content]

        content = " ".join(args) if not reply else reply.text or ""
        if not content.strip():
            return None

        return [None, content]

    async def _bulk_send(self, message, content: str, count: int):
        await message.delete()
        self.running = True

        for _ in range(count):
            if not self.running:
                break
            await message.respond(content)

    async def _show_help(self, message, command: str):
        commands = {
            "spam": ".spam <кількість:int> <текст або відповідь>",
            "cspam": ".cspam <текст або відповідь>",
            "wspam": ".wspam <текст або відповідь>",
            "delayspam": ".delayspam <затримка:float> <кількість:int> <текст або відповідь>",
            "reverse": ".reverse <текст або відповідь>",
        }
        usage = commands.get(command, "")
        await message.respond(f"\u274c Неправильне використання. {usage}")
