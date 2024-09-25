# meta developer: @SodaModules

import requests
import socket
from .. import loader, utils

API_URL = "https://ipinfo.io/{}/json"
API_KEY = "97e9cfcd633bb0"

class IPInfoMod(loader.Module):
    """Модуль для отримання інформації про IP-адресу або домен за допомогою IPinfo API"""
    strings = {
        "name": "IPInfo",
        "invalid_ip": "Неправильний формат IP-адреси або доменного імені.",
        "ip_info": "Інформація про IP-адресу {ip}:\n{info}",
        "ip_info_error": "Не вдалося отримати інформацію про IP-адресу.",
        "dns_lookup_error": "Не вдалося знайти IP-адресу для доменного імені {domain}."
    }

    async def ipinfocmd(self, message):
        """Отримати інформацію про IP-адресу або домен: .ipinfo <IP-адреса або домен>"""
        args = utils.get_args(message)
        if len(args) < 1:
            await message.edit("Будь ласка, надайте IP-адресу або домен для перевірки.")
            return

        query = args[0]
        ip_address = self._resolve_to_ip(query)
        if not ip_address:
            await message.edit(self.strings("invalid_ip"))
            return

        info = await self._get_ip_info(ip_address)
        if info:
            info_text = (
                f"IP-адреса: {info.get('ip', 'N/A')}\n"
                f"Місто: {info.get('city', 'N/A')}\n"
                f"Область: {info.get('region', 'N/A')}\n"
                f"Країна: {info.get('country', 'N/A')}\n"
                f"Організація: {info.get('org', 'N/A')}\n"
                f"Інформація про локацію: {info.get('loc', 'N/A')}"
            )
            await message.edit(self.strings("ip_info").format(ip=ip_address, info=info_text))
        else:
            await message.edit(self.strings("ip_info_error"))

    def _resolve_to_ip(self, query):
        """Перетворення доменного імені на IP-адресу, якщо це необхідно"""
        try:
            # Перевірка, чи це домен
            socket.inet_aton(query)
            return query
        except socket.error:
            # Спроба перетворення доменного імені на IP
            try:
                return socket.gethostbyname(query)
            except socket.error:
                return None

    async def _get_ip_info(self, ip):
        """Отримання інформації про IP-адресу з IPinfo API"""
        url = API_URL.format(ip)
        response = requests.get(url, params={'token': API_KEY})
        if response.status_code == 200:
            return response.json()
        return None
