import asyncio
import nodriver

async def main():
    browser = await nodriver.start(headless=False)
    page = await browser.get("https://hyperdash.info/top-traders")


    # Click the Filters button by its visible text
    filters_button = await page.find("Filters", best_match=True)
    if filters_button:
        await filters_button.click()
        print("Filters button clicked.")
    else:
        print("Filters button not found.")
    ticker = await page.find("All Coins", best_match=True)
    if ticker:
        await ticker.click()
    await ticker.send_keys("BTC")
    btc = await page.find("BTC", best_match=True)
    if btc:
        await btc.click()


asyncio.run(main())
