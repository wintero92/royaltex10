import threading

import sys
import sklearn
from numpy import array
from pandas import DataFrame, concat
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as pwTimeoutError
from playwright.sync_api import sync_playwright

URL = "https://www.ebay.com/usr/royaltex10"


class Royaltex10List:
    def __init__(self, url) -> None:
        self.url = url
        self.urls = []
        self.titles = []

    def next_page(self, page: Page):
        next = '//a[@aria-label="Go to next search page"]'
        element = page.locator(next)
        try:
            element.click()
            return True
        except pwTimeoutError:
            return False

    def get_items(self, page: Page):
        elements = page.locator(
            '//div[@id="srp-river-results"]//div[@class="s-item__info clearfix"]'
        )
        n_elements = elements.count()
        for i in range(n_elements):
            element = elements.nth(i)
            title = element.locator('//span[@role="heading"]').inner_text()
            url = element.locator('//a[@class="s-item__link"]').get_attribute("href")
            self.titles.append(title)
            self.urls.append(url)

    def run(self):
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(locale="en-GB")
        page = context.new_page()

        page.goto(self.url)

        page.click(
            '//button[@aria-label="Accept privacy terms and settings"]'
        )  # cookies
        page.wait_for_load_state("load")
        page.click(
            '//div[@class="str-marginals str-marginals__footer"]//a[contains(., "See All")]'
        )
        page.wait_for_load_state("load")
        page.click('//span[@id="srp-ipp-menu"]//button')
        page.click('//span[@id="srp-ipp-menu-content"]//span[contains(., "240")]')
        page.wait_for_load_state("load")

        while True:
            page.wait_for_load_state("load")
            self.get_items(page)
            if not self.next_page(page):
                break

        browser.close()
        playwright.stop()

    def save(self):
        with open("list_urls.txt", mode="w", encoding="utf-8") as file:
            file.write("\n".join(self.urls))
            file.write("\n")
        with open("list_titles.txt", mode="w", encoding="utf-8") as file:
            file.write("\n".join(self.titles))
            file.write("\n")


class Royaltex10Sort:
    def __init__(self, data: DataFrame) -> None:
        self.data = data
        self.data = self.data[~self.data.title.str.lower().str.contains("poly")]
        self.data = self.data[~self.data.title.str.lower().str.contains("poli")]
        self.data = self.data[~self.data.title.str.lower().str.contains("pole")]
        self.data["hash"] = self.data["url"].str.split(":").str[-1]
        self.data.sort_values(by="hash", inplace=True, ignore_index=True)
        self.to_be_uniq = list(set(self.data["hash"].to_list()))
        self.uniq = DataFrame({"url": [], "title": []})

    @staticmethod
    def _add(dataframe, new_row):
        return concat([dataframe, DataFrame(new_row)], ignore_index=True)

    def _add_custom(self, dataframe, url, title):
        return self._add(dataframe, {"url": [url], "title": [title]})

    def _iter(self, sema, hash):
        sema.acquire()
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(1000000)
        to_be_checked = self.data[self.data["hash"] == hash]
        for _, row in sklearn.utils.shuffle(to_be_checked).iterrows():
            page.goto(row["url"])
            price = page.locator('//div[@data-testid="x-price-primary"]').inner_text()
            if "GBP" in price:
                self.uniq = self._add_custom(self.uniq, row["url"], row["title"])
                break
        print(f"Number of items: {len(self.uniq)}/{len(self.to_be_uniq)}.")
        context.close()
        browser.close()
        playwright.stop()
        sema.release()

    def run(self):
        maxthreads = 16
        sema = threading.Semaphore(value=maxthreads)
        threads = list()
        for _, hash in enumerate(self.to_be_uniq):
            thread = threading.Thread(
                target=self._iter,
                args=(
                    sema,
                    hash,
                ),
            )
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()

    def save(self):
        self.uniq.to_csv("sorted.csv")


if __name__ == "__main__":
    if sys.argv[1] == "list":
        royaltex10list = Royaltex10List(URL)
        royaltex10list.run()
        royaltex10list.save()
    if sys.argv[1] == "sort":
        with open("list_urls.txt", mode="r", encoding="utf-8") as file:
            urls = array(file.read().splitlines())
        with open("list_titles.txt", mode="r", encoding="utf-8") as file:
            titles = array(file.read().splitlines())
        data = DataFrame({"url": urls, "title": titles})
        royaltex10sort = Royaltex10Sort(data)
        royaltex10sort.run()
        royaltex10sort.save()
