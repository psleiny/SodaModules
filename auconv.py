# ---------------------------------------------------------------------------------
# Name: AuConv
# Description: Конвертування аудіо файлів у різні формати
# Author: @SodaModules
# ---------------------------------------------------------------------------------
# meta developer: @SodaModules
# scope: AuConv
# scope: AuConv 1.0.1
# requires: pydub.py
# ---------------------------------------------------------------------------------

from pydub import AudioSegment
from .. import loader, utils
from telethon import types
import io

@loader.tds
class AuConvMod(loader.Module):
    """Конвертування аудіо файлів у різні формати"""
    strings = {'name': 'AuConv',
               'no_reply': 'А де реплай? <emoji document_id=5433752551407230901>🙄</emoji>',
               'not_audio': 'Це не аудіофайл<emoji document_id=5274099962655816924>❗️</emoji>',
               'is_voice': 'Це войс, а не аудіофайл<emoji document_id=5274099962655816924>❗️</emoji>',
               'downloading': '<emoji document_id=5258336354642697821>⬇️</emoji> Завантажуємо',
               'converting': '<emoji document_id=5258331647358540449>✍️</emoji> Робимо войс',
               'exporting': '<emoji document_id=5258043150110301407>⬆️</emoji> Єкспорт',
               'sending': '<emoji document_id=5260450573768990626>➡️</emoji> Відправляємо',
               'unsupported_format': 'Я хз що таке {}<emoji document_id=5427052514094619126>🤷‍♀️</emoji>',
               'specify_format': '<emoji document_id=5877396173135811032>⌨</emoji> Вкажіть формат'}

    async def client_ready(self, client, db):
        self._client = client

    async def tovoicecmd(self, message):
        """.tovoice <reply to audio>
        Сконвертувати аудіо в войс
        """
        reply = await message.get_reply_message()
        if not reply:
            await utils.answer(message, self.strings['no_reply'])
            return

        try:
            if reply.media.document.attributes[0].voice:
                await utils.answer(message, self.strings['is_voice'])
                return
        except:
            await utils.answer(message, self.strings['not_audio'])
            return

        await utils.answer(message, self.strings['downloading'])
        au = io.BytesIO()
        await message.client.download_media(reply.media.document, au)
        au.seek(0)
        await utils.answer(message, self.strings['converting'])

        audio = AudioSegment.from_file(au)
        m = io.BytesIO()
        m.name = "voice.ogg"
        audio.split_to_mono()

        await utils.answer(message, self.strings['exporting'])
        dur = len(audio) / 1000
        audio.export(m, format="ogg", bitrate="64k", codec="libopus")

        await utils.answer(message, self.strings['sending'])
        m.seek(0)
        await message.client.send_file(message.to_id, m, reply_to=reply.id, voice_note=True, duration=dur)
        await message.delete()

    async def toformatcmd(self, message):
        """.toformat [format] <reply to audio>
        Сконвертувати аудіо/відео/войс у потрібний формат
        Підтримується mp3, m4a, ogg, mpeg, wav, oga
        """
        frmts = ['ogg', 'mpeg', 'mp3', 'wav', 'oga', 'm4a', '3gp']
        reply = await message.get_reply_message()
        if not reply:
            await utils.answer(message, self.strings['no_reply'])
            return

        try:
            duration = reply.media.document.attributes[0].duration
            formatik = utils.get_args_raw(message)
            if not formatik:
                await utils.answer(message, self.strings['specify_format'])
                return
            if formatik not in frmts:
                await utils.answer(message, self.strings['unsupported_format'].format(formatik))
                return
        except:
            await utils.answer(message, self.strings['not_audio'])
            return

        await utils.answer(message, self.strings['downloading'])
        au = io.BytesIO()
        await message.client.download_media(reply.media.document, au)
        au.seek(0)

        await utils.answer(message, self.strings['converting'].format(formatik))
        audio = AudioSegment.from_file(au)
        m = io.BytesIO()
        m.name = f"Converted_to.{formatik}"
        audio.split_to_mono()

        await utils.answer(message, self.strings['exporting'])
        audio.export(m, format=formatik)

        await utils.answer(message, self.strings['sending'])
        m.seek(0)
        await message.client.send_file(
            message.to_id, 
            m, 
            reply_to=reply.id, 
            attributes=[types.DocumentAttributeAudio(duration=duration, title=f"Converted to {formatik}", performer="@Sekai_Yoneya")]
        )
        await message.delete()
