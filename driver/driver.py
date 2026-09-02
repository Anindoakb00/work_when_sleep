from pathlib import Path
import time
import random
from typing import List, Optional, Union
from urllib.parse import urlparse, parse_qs, unquote

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# Chrome options: quote paths to avoid parsing issues on Windows
chrome_options = Options()
project_directory = Path(__file__).resolve().parents[1]
userdata_directory = project_directory / "userdata"
userdata_directory.mkdir(exist_ok=True)

chrome_options.add_argument("--start-maximized")
# If using a profile name with spaces, quoting helps the arg parser
chrome_options.add_argument('--profile-directory="Profile 3"')
prefs = {"profile.default_content_setting_values.notifications": 2}
chrome_options.add_experimental_option("prefs", prefs)
chrome_options.add_argument("--disable-infobars")
chrome_options.add_experimental_option("useAutomationExtension", False)
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
# Quote the user-data-dir path so Chrome receives it correctly on Windows
chrome_options.add_argument(f'--user-data-dir="{str(userdata_directory)}"')


def _human_typing(element, text: str, min_delay: float = 0.03, max_delay: float = 0.12):
    """Send keys char-by-char with small random delays to simulate a human typing."""
    for ch in text:
        element.send_keys(ch)
        time.sleep(random.uniform(min_delay, max_delay))


def _extract_target_url(href: Optional[str]) -> Optional[str]:
    """Normalize Google redirect links and return a clean target URL.
    Returns None for non-navigable or internal Google links.
    """
    if not href:
        return None
    href = href.strip()
    # Google uses /url?q=<target>&... or full absolute with '/url?q='
    if href.startswith('/url') or '/url?' in href or '/url?q=' in href:
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        q = qs.get('q')
        if q:
            return unquote(q[0])
    # Some results already have full hrefs
    return href


def _is_unwanted(url: str) -> bool:
    """Filter out Google-internal, cache, account, maps, or javascript links."""
    if not url:
        return True
    low = url.lower()
    unwanted_markers = [
        'webcache.googleusercontent',
        'accounts.google.com',
        'google.com/search',
        'support.google.com',
        'maps.google',
        'javascript:void',
    ]
    return any(m in low for m in unwanted_markers)


class Driver:
    def __init__(self, implicit_wait: int = 5, page_load_timeout: int = 30):
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.implicitly_wait(implicit_wait)
        self.driver.set_page_load_timeout(page_load_timeout)

    def get(self, url: str, wait_ready: bool = True, timeout: int = 15):
        """Navigate to a URL and optionally wait until document.readyState == 'complete'."""
        self.driver.get(url)
        if wait_ready:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )

    def _search_single(self, query_term: str, click_first: bool,
                       preferred_domains: Optional[List[str]], timeout: int) -> Optional[str]:
        """Perform a single-term Google search and try to navigate to a result."""
        # Open Google home
        self.get("https://www.google.com/", wait_ready=True, timeout=timeout)

        # Accept cookie banner if present (best-effort)
        try:
            accept = WebDriverWait(self.driver, 2).until(
                EC.element_to_be_clickable((By.XPATH, "//button//*[contains(text(), 'I agree') or contains(text(),'Accept')]/.."))
            )
            accept.click()
            time.sleep(0.3)
        except Exception:
            pass

        # Type into search box
        search_box = WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((By.NAME, "q"))
        )
        search_box.clear()
        _human_typing(search_box, query_term)
        search_box.send_keys(Keys.ENTER)

        # Wait for results container
        WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((By.ID, "search"))
        )

        # Gather anchors that have titles (<h3>) inside result blocks
        anchors = self.driver.find_elements(By.TAG_NAME, "a")
        candidates = []
        seen = set()
        for a in anchors:
            try:
                if not a.find_elements(By.TAG_NAME, 'h3'):
                    continue
                raw = a.get_attribute('href')
                target = _extract_target_url(raw)
                if not target or _is_unwanted(target):
                    continue
                if target in seen:
                    continue
                seen.add(target)
                title = a.text or ''
                candidates.append((target, title, a))
            except Exception:
                continue

        # reorder candidates to prefer preferred_domains
        if preferred_domains:
            preferred = []
            others = []
            for t, title, anchor in candidates:
                if any(d.lower() in t.lower() for d in preferred_domains):
                    preferred.append((t, title, anchor))
                else:
                    others.append((t, title, anchor))
            candidates = preferred + others

        # Try each candidate: click and verify navigation
        for target, title, anchor in candidates:
            try:
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", anchor)
                    time.sleep(random.uniform(0.2, 0.6))
                    anchor.click()
                except Exception:
                    self.get(target, wait_ready=True, timeout=timeout)

                WebDriverWait(self.driver, timeout).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )

                current = self.driver.current_url
                if 'google.com/search' in current or 'accounts.google.com' in current or 'webcache.googleusercontent' in current:
                    try:
                        self.driver.back()
                        time.sleep(0.5)
                    except Exception:
                        pass
                    continue

                return current
            except Exception:
                try:
                    self.driver.back()
                    time.sleep(0.3)
                except Exception:
                    pass
                continue

        return None

    def search_google(self, query: Union[str, List[str]], click_first: bool = True,
                      preferred_domains: Optional[List[str]] = None,
                      timeout: int = 15) -> Optional[str]:
        """
        Accepts either a single string or a list of single-term queries.
        If a multi-word string is provided, it is split into individual terms and
        searched sequentially: the first term is searched globally, and subsequent
        terms are searched while preferring the domain found for the first term.
        Returns the last successful navigation (or the first success if only one term).
        """
        terms: List[str]
        if isinstance(query, (list, tuple)):
            terms = [str(q).strip() for q in query if str(q).strip()]
        else:
            s = str(query).strip()
            if ' ' in s:
                # split into single-word terms; preserve quoted phrases as single terms could be complex
                terms = [t for t in s.split() if t]
            else:
                terms = [s] if s else []

        if not terms:
            return None

        # If only a single term, behave as before
        if len(terms) == 1:
            return self._search_single(terms[0], click_first, preferred_domains, timeout)

        # Search first term globally (respecting preferred_domains if given)
        first = terms[0]
        first_result = self._search_single(first, click_first, preferred_domains, timeout)
        if not first_result:
            # fallback: try the remaining terms independently (old behavior)
            for term in terms[1:]:
                r = self._search_single(term, click_first, preferred_domains, timeout)
                if r:
                    return r
            return None

        # extract domain from first_result to prefer for subsequent searches
        try:
            parsed = urlparse(first_result)
            domain = parsed.netloc
            if domain.startswith('www.'):
                domain = domain[4:]
        except Exception:
            domain = None

        last_success = first_result
        # For each subsequent term, prefer results from the same domain
        for term in terms[1:]:
            pref = [domain] if domain else None
            r = self._search_single(term, click_first, pref, timeout)
            if r:
                last_success = r
            else:
                # try without domain preference as a fallback
                r2 = self._search_single(term, click_first, preferred_domains, timeout)
                if r2:
                    last_success = r2
                else:
                    continue

        return last_success

    def navigate_search_result(self, query: str, domain: Optional[str] = None) -> Optional[str]:
        """Convenience wrapper: search and navigate to first result; prefer domain if given."""
        preferred = [domain] if domain else None
        return self.search_google(query, click_first=True, preferred_domains=preferred)

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Example usage:
# with Driver() as d:
#     d.navigate_search_result('site:example.com your search terms', domain='example.com')
