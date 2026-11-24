"""Bounded source research. No guessed facts or external account access."""
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from app.services.safe_fetch import fetch_public_html
from app.services.identity import digest


class ResearchAgent:
    async def research(self, company: str, urls: list[str]) -> dict:
        sources, warnings = [], []
        for index, url in enumerate(urls[:3], 1):
            try:
                html = await fetch_public_html(url)
                page = BeautifulSoup(html, 'html.parser')
                title = page.title.get_text(' ', strip=True)[:200] if page.title else company
                for node in page(['script', 'style', 'nav', 'footer', 'header', 'noscript', 'form']):
                    node.decompose()
                content = ' '.join(page.get_text(' ', strip=True).split())
                if len(content) < 80:
                    raise ValueError('Insufficient source text')
                sources.append({'url': url, 'title': title, 'excerpt': content[:1800],
                                'fetched_at': datetime.now(timezone.utc).isoformat(), 'content_digest': digest(content)})
            except Exception:
                warnings.append(f'Source {index} could not be read. Check the URL or try another public page.')
        return {'company': company, 'sources': sources, 'warnings': warnings}
