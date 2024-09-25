# meta developer: @SodaModules

from .. import loader
from asyncio import sleep

@loader.tds
class ayanami(loader.Module):
    """Хто я?"""

    strings = {"name": "Аянамі рей"}

    @loader.owner
    async def ayanamicmd(self, message):
        """Аянамі Рей"""
        global text
        text = ""
        for index, ayanami_line in enumerate(["Хто я?",
                        "Аянамі Рей.",
                        "А хто ти?",
                        "Аянамі Рей.",
                        "Ти теж Аянамі Рей?",
                        "Так. Я та, кого знають як Аянамі Рей.",
                        "Ми усі ті, кого знають, як Аянамі Рей.",
                        "Як вони усі можуть бути мною?",
                        "Просто тому що інщі звуть нас Аянамі Рей. Тільки і все. В тебе несправжня душа, і тіло твое - підробка. Знаєш чому?",
                        "Я не несправжня і не підробка. Я - це я.",
                        "Ні, ти всього лиш оболонка з піддробленною душею, створенна чоловіком по імені Гєндо Ікарі. Ти всього лиш те, що прикидуеться людиною. Ось, прислухайся до себе. Відчуваеш цю невловиму, майже невідрізниму істоту, сховану у твоїх самих моторошніх снах? Саме це і є ти."]):
            delay = 3
            if index in [0, 1, 2, 3]:
                delay = 2
            elif index in [8, 9, 10]:
                delay = 7
            text += ayanami_line + "\n"
            await message.edit(text)
            await sleep(delay)
