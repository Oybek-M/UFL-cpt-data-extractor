"""Rate-limitli HTTP klient va robots.txt siyosati.

Manba: website-to-txt-collector/continuous_collector.py (605-645) — UFL uslubida port.
UFL httpx'da standartlashgani uchun `requests` o'rniga `httpx` ishlatiladi. WebClient
xost bo'yicha minimal kechikishni ta'minlaydi (maqsad-serverga odobli yuk); testlar
uchun klient DI orqali injektlanadi.
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.robotparser

import httpx


class WebClient:
    def __init__(
        self,
        *,
        user_agent: str,
        request_delay: float,
        timeout: float,
        client: httpx.Client | None = None,
    ) -> None:
        self._client = client or httpx.Client(
            headers={"User-Agent": user_agent}, follow_redirects=True
        )
        self._delay = request_delay
        self._timeout = timeout
        self._last_request: dict[str, float] = {}

    def get(self, url: str) -> httpx.Response:
        host = urllib.parse.urlsplit(url).netloc.lower()
        elapsed = time.monotonic() - self._last_request.get(host, 0.0)
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)
        response = self._client.get(url, timeout=self._timeout)
        self._last_request[host] = time.monotonic()
        response.raise_for_status()
        return response

    def close(self) -> None:
        self._client.close()


class RobotsPolicy:
    def __init__(self, seed: str, web: object, *, user_agent: str) -> None:
        parsed = urllib.parse.urlsplit(seed)
        self.user_agent = user_agent
        self.robots_url = urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, "/robots.txt", "", "")
        )
        self.parser = urllib.robotparser.RobotFileParser()
        self.parser.set_url(self.robots_url)
        self.sitemaps: list[str] = []
        try:
            lines = web.get(self.robots_url).text.splitlines()  # type: ignore[attr-defined]
            self.parser.parse(lines)
            for line in lines:
                if line.lower().startswith("sitemap:"):
                    location = line.split(":", 1)[1].strip()
                    if location:
                        self.sitemaps.append(location)
        except Exception:  # noqa: BLE001 — robots.txt yo'q/yuklanmadi: hammaga ruxsat + standart sitemap
            self.parser.parse([])
        if not self.sitemaps:
            self.sitemaps.append(
                urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/sitemap.xml", "", ""))
            )

    def allowed(self, url: str) -> bool:
        return self.parser.can_fetch(self.user_agent, url)
