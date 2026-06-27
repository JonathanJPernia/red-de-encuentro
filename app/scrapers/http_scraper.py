from abc import abstractmethod

import httpx

from app.scrapers.base_scraper import BaseScraper


class HttpScraper(BaseScraper):
    """BaseScraper que descarga contenido HTTP con httpx."""

    timeout: float = 30.0
    headers: dict[str, str] = {
        "User-Agent": "BotTL/0.1 (+https://github.com/bot-tl; missing-persons search bot)",
    }

    @abstractmethod
    def target_url(self) -> str:
        """URL concreta a descargar."""
        raise NotImplementedError

    def fetch(self) -> str:
        url = self.target_url()
        with httpx.Client(timeout=self.timeout, headers=self.headers, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text
