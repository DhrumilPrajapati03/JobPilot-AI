"""Bounded public-page fetching with DNS pinning and per-redirect validation.

Connect to a validated IP while preserving the original Host and TLS hostname.
This closes the validation/connect DNS-rebinding gap. Environment proxies are
disabled so they cannot independently resolve the original hostname.
"""

import asyncio
import ipaddress
import socket

import httpx

MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 4


class UnsafeURL(ValueError):
    pass


async def public_target(value: str) -> tuple[httpx.URL, str]:
    try:
        url = httpx.URL(value)
        if (url.scheme not in {"http", "https"} or not url.host or url.userinfo
                or url.port not in {None, 80 if url.scheme == "http" else 443}
                or "%" in url.host):
            raise UnsafeURL("Use a public HTTP/HTTPS URL on its standard port, without credentials.")
        addresses = await asyncio.get_running_loop().getaddrinfo(
            url.host, url.port or (443 if url.scheme == "https" else 80), type=socket.SOCK_STREAM,
        )
        ips = list(dict.fromkeys(item[4][0] for item in addresses))
        if not ips:
            raise UnsafeURL("The job URL did not resolve to a public address.")
        for value in ips:
            ip = ipaddress.ip_address(value)
            # Reject mapped/transitional IPv6 as well as non-public destinations.
            if not ip.is_global or ip.is_multicast or ip.is_reserved or (isinstance(ip, ipaddress.IPv6Address) and
                                   (ip.ipv4_mapped or ip.sixtofour or ip.teredo)):
                raise UnsafeURL("Job URLs must resolve only to public internet addresses.")
        return url, ips[0]
    except (httpx.InvalidURL, socket.gaierror, ValueError) as exc:
        if isinstance(exc, UnsafeURL):
            raise
        raise UnsafeURL("The job URL is invalid or cannot be resolved.") from exc


async def fetch_public_html(value: str) -> str:
    async with asyncio.timeout(25):
        for hop in range(MAX_REDIRECTS + 1):
            original, address = await public_target(value)
            pinned = original.copy_with(host=address, fragment=None)
            host = original.raw_host.decode("ascii")
            if ":" in host:
                host = f"[{host}]"
            headers = {
                "Host": host,
                "User-Agent": "JobPilotAI/1.0 (job description reader)",
                "Accept": "text/html,text/plain;q=0.9",
                "Accept-Encoding": "identity",
            }
            # A fresh client per hop avoids cookies and connection-pool TLS reuse
            # across two different hostnames which happen to share an IP.
            async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client:
                async with client.stream("GET", pinned, headers=headers,
                                         extensions={"sni_hostname": original.raw_host.decode("ascii")}) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location or hop == MAX_REDIRECTS:
                            raise UnsafeURL("The job URL has an invalid or excessive redirect chain.")
                        value = str(original.join(location))
                        continue
                    if response.status_code != 200:
                        raise UnsafeURL(f"The job page returned HTTP {response.status_code}.")
                    media_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                    if media_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
                        raise UnsafeURL("The job URL must return an HTML or text page.")
                    if response.headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
                        raise UnsafeURL("Compressed job pages are not accepted; paste the description instead.")
                    length = response.headers.get("content-length")
                    if length and (not length.isdigit() or int(length) > MAX_PAGE_BYTES):
                        raise UnsafeURL("The job page exceeds the 2 MiB size limit.")
                    body = bytearray()
                    async for chunk in response.aiter_raw(chunk_size=64 * 1024):
                        body.extend(chunk)
                        if len(body) > MAX_PAGE_BYTES:
                            raise UnsafeURL("The job page exceeds the 2 MiB size limit.")
                    return body.decode(response.encoding or "utf-8", errors="replace")
    raise UnsafeURL("Unable to retrieve the job description.")
