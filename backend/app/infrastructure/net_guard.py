"""SSRF-защита исходящих вебхуков: только http/https и (по умолчанию) только публичные адреса."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeUrl(ValueError):
    pass


def _is_forbidden(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def check_url(url: str, allow_private: bool, resolve: bool = True) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeUrl("Разрешены только http:// и https://")
    if not parts.hostname:
        raise UnsafeUrl("В адресе нет хоста")
    if parts.username or parts.password:
        raise UnsafeUrl("Логин/пароль в URL не допускаются — используйте секрет вебхука")
    if allow_private:
        return
    host = parts.hostname
    try:
        ips = [ipaddress.ip_address(host)]
    except ValueError:
        if host.lower() in ("localhost",) or host.lower().endswith(".localhost"):
            raise UnsafeUrl("Адреса localhost запрещены (WEBHOOK_ALLOW_PRIVATE=false)") from None
        if not resolve:
            return
        try:
            infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            raise UnsafeUrl(f"Не удалось разрешить имя {host}") from None
        ips = [ipaddress.ip_address(i[4][0]) for i in infos]
    for ip in ips:
        if _is_forbidden(ip):
            raise UnsafeUrl(f"Адрес {ip} внутренний (loopback/private/link-local) — запрещено (WEBHOOK_ALLOW_PRIVATE=false)")
