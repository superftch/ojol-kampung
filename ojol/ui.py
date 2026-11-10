import asyncio
import json
import re

from .mcp_browser import BrowserError
from .models import Product
from .planner import decimal_id, parse_snapshot

SNAPSHOT_JS = """(() => {
 const root=document.querySelector('#ks-ojol');
 const wallet=document.querySelector('button[title="Koin cash (di dompet)"]');
 if(!root || !wallet) return {error:'Panel Ojol atau dompet cash tidak tersedia'};
 const tiles={};
 for(const label of root.querySelectorAll('span')) {
   if(['Bensin','Kondisi','Kuota HP','Hasil hari ini'].includes(label.textContent.trim()))
     tiles[label.textContent.trim()]=label.parentElement.querySelector('strong')?.textContent.trim();
 }
 return {text:root.innerText,tiles,wallet:wallet.textContent,
   buttons:[...root.querySelectorAll('button')].map(b=>({text:b.textContent.trim(),disabled:b.disabled})),
   trip:root.querySelector('p')?.textContent+' | '+root.querySelector('p:nth-of-type(2)')?.textContent,
   history:[...root.querySelectorAll('li')].map(x=>x.textContent.trim())};
})()"""


class GameUI:
    def __init__(self, browser, check_cancel=lambda: None):
        self.browser = browser
        self.check_cancel = check_cancel

    async def pause(self):
        await asyncio.sleep(0.35)
        self.check_cancel()

    async def click_selector(self, selector):
        self.check_cancel()
        return await self.browser.js(
            "(() => {const matches=[...document.querySelectorAll(" + json.dumps(selector) + ")];"
            "if(matches.length!==1 || matches[0].disabled)return {error:'Kontrol UI hilang/ambigu/nonaktif'};matches[0].click();return true;})()"
        )

    async def close_views(self):
        if await self.browser.js("!!document.querySelector('[data-testid=\"tujuan-cari\"]')"):
            await self.click_selector('#tujuan-title + button[aria-label="Tutup"]')
            await self.pause()
        if await self.browser.js("!!document.querySelector('[data-testid=\"panel\"]')"):
            await self.click_selector('[data-testid="panel"] [aria-label="Tutup panel"]')
            await self.pause()
        if await self.browser.js("!!document.querySelector('[data-testid=\"rumah-keluar\"]')"):
            await self.click_selector('[data-testid="rumah-keluar"]')
            await self.pause()

    async def work(self):
        if not await self.browser.js("!!document.querySelector('#ks-ojol')"):
            await self.close_views()
            await self.click_selector('[data-tour="nav-kerja"]')
            await self.pause()
        for _ in range(20):
            found = await self.browser.js("!!document.querySelector('[data-testid=\"ojol-fold\"]')")
            if found:
                break
            await self.pause()
        if not found:
            raise BrowserError(
                "Ojol desa belum tersedia; login, kepemilikan kendaraan, atau sesi perlu diperiksa manual"
            )
        collapsed = await self.browser.js(
            "document.querySelector('[aria-controls=\"fold-kerja-ojol\"]')?.getAttribute('aria-expanded')==='false'"
        )
        if collapsed:
            await self.click_selector('[aria-controls="fold-kerja-ojol"]')
            await self.pause()

    async def snapshot(self):
        await self.work()
        return parse_snapshot(await self.browser.js(SNAPSHOT_JS))

    async def open_shop(self, resource):
        queries = {"fuel": "spbu", "condition": "bengkel", "data": "konter"}
        preferred = {
            "fuel": "SPBU Utara 1",
            "condition": "Akademis.ai Motor",
            "data": "Konter kang ANU",
        }
        categories = {"fuel": "SPBU", "condition": "Bengkel motor", "data": "Konter pulsa"}
        await self.close_views()
        await self.click_selector('[data-testid="tujuan-btn"]')
        await self.pause()
        self.check_cancel()
        await self.browser.js(
            "(() => {const input=document.querySelector('[data-testid=\"tujuan-cari\"]');"
            "if(!input)return {error:'Pencarian tidak tersedia'};Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,"
            + json.dumps(queries[resource])
            + ");input.dispatchEvent(new Event('input',{bubbles:true}));return true;})()"
        )
        await self.pause()
        if await self.browser.js(
            "document.querySelector('[data-testid=\"tujuan-buka-saja\"]')?.getAttribute('aria-checked')==='false'"
        ):
            await self.click_selector('[data-testid="tujuan-buka-saja"]')
            await self.pause()
        rows = await self.browser.js(
            "[...document.querySelectorAll('[data-testid=\"tujuan-item\"]')].map(row=>({name:row.querySelector('b')?.textContent.trim(),text:row.textContent.replace(/\\s+/g,' ').trim(),hours:row.querySelector('[data-testid=\"tujuan-jam\"]')?.textContent}))"
        )
        valid = [
            row
            for row in rows
            if categories[resource].casefold() in row["text"].casefold()
            and row.get("hours")
            and "buka" in row["hours"].casefold()
            and not re.search(r"Tutup|Belum", row["hours"], re.IGNORECASE)
        ]
        if not valid:
            raise BrowserError(f"Tidak ada toko {queries[resource]} yang terbukti sedang buka")
        selected = next((row for row in valid if row["name"] == preferred[resource]), valid[0])
        self.check_cancel()
        self.last_navigation = await self.browser.js(
            "(() => {const rows=[...document.querySelectorAll('[data-testid=\"tujuan-item\"]')].filter(x=>x.textContent.replace(/\\s+/g,' ').trim()==="
            + json.dumps(selected["text"])
            + ");if(rows.length!==1)return {error:'Toko berubah/ambigu'};const eye=rows[0].querySelector('button[title=\"Lihat di peta\"]');"
            "if(!eye || eye.disabled)return {error:'Tombol mata tidak tersedia'};const evidence={method:'eye_preview',label:eye.getAttribute('aria-label'),button:eye.textContent.trim()};eye.click();return evidence;})()"
        )
        await self.pause()
        identity_verified = False
        for _ in range(30):
            identity_verified = await self.browser.js(
                "!!document.querySelector('[data-testid=\"panel\"]')?.textContent.includes("
                + json.dumps(selected["name"])
                + ")"
            )
            if identity_verified:
                break
            await self.pause()
        if not identity_verified:
            raise BrowserError("Identitas toko setelah klik mata belum terverifikasi")
        self.last_navigation.update(
            shop=selected["name"], tab_id=self.browser.tab_id, panel_verified=True
        )
        # Shop identity renders before its fetched catalog; wait only for reads, never repeat the eye click.
        for _ in range(30):
            products = await self.products()
            if products:
                return selected["name"], products
            await self.pause()
        raise BrowserError(
            "Katalog toko belum tersedia setelah 10 detik", stage="shop.catalog_loading"
        )

    async def products(self):
        rows = await self.browser.js(
            "(() => {const p=document.querySelector('[data-testid=\"panel\"]');if(!p)return {error:'Panel toko tidak tersedia'};"
            "return [...p.querySelectorAll('button')].filter(b=>b.textContent.trim()==='Beli').map(b=>({name:b.parentElement.querySelector('strong')?.textContent.trim(),"
            "details:b.parentElement.querySelector('small')?.textContent.trim(),row_text:b.parentElement.textContent.replace(/\\s+/g,' ').trim(),enabled:!b.disabled}));})()"
        )
        products = []
        for row in rows:
            details = row.get("details") or ""
            price = re.match(r"([\d.,]+)\s*koin\b", details)
            if not price or not row.get("name"):
                continue
            effects = {}
            for symbol, key in (("⛽", "fuel"), ("🔧", "condition"), ("📶", "data")):
                effect = re.search(re.escape(symbol) + r"\s*\+\s*(\d+)", details)
                if effect:
                    effects[key] = int(effect[1])
            products.append(
                Product(
                    name=row["name"],
                    price=decimal_id(price[1]),
                    effects=effects,
                    row_text=row["row_text"],
                    enabled=row["enabled"],
                )
            )
        return products

    async def buy(self, product: Product, expected_wallet, min_balance=0):
        self.check_cancel()
        # Only exact observed in-game product rows; no navigation, top-up, request replay, or arbitrary click.
        return await self.browser.js(
            "(() => {const wallet=document.querySelector('button[title=\"Koin cash (di dompet)\"]')?.textContent;"
            "const rows=[...document.querySelectorAll('[data-testid=\"panel\"] button')].filter(b=>b.textContent.trim()==='Beli' && b.parentElement.textContent.replace(/\\s+/g,' ').trim()==="
            + json.dumps(product.row_text)
            + ");if(rows.length!==1 || rows[0].disabled)return {error:'Harga/item berubah atau tidak tersedia'};"
            "const m=wallet?.match(/([\\d.,]+)\\s*koin/);const balance=m?Number(m[1].replace(/\\./g,'').replace(',','.')):null;"
            "if(balance!=="
            + str(expected_wallet)
            + ")return {error:'Dompet berubah sebelum pembelian'};"
            "if(balance-"
            + str(product.price)
            + "<"
            + str(min_balance)
            + ")return {error:'Pembelian melewati saldo minimum'};rows[0].click();return {clicked:true};})()"
        )

    async def job_click(self, expected_label: str):
        self.check_cancel()
        # Scope strictly to Ojol; labels such as Pindah/Berhenti bekerja never enter this function.
        return await self.browser.js(
            "(() => {const buttons=[...document.querySelectorAll('#ks-ojol button')].filter(b=>b.textContent.trim()==="
            + json.dumps(expected_label)
            + ");if(buttons.length!==1 || buttons[0].disabled)return {error:'Tombol job berubah/ambigu/nonaktif'};buttons[0].click();return {clicked:true};})()"
        )
