from typing import NamedTuple


class ShopLocation(NamedTuple):
    id: str
    plot_id: str
    name: str
    x: int
    y: int


class NeedShop(NamedTuple):
    id: str
    plot_id: str
    name: str
    category: str


SHOPS_BY_VILLAGE = {
    "desa-utara": {
        "fuel": (
            ShopLocation(
                "2106025d-77ac-4a49-8520-8d84740ef17f", "M25-U09", "SPBU Utara 1", 30, -133
            ),
            ShopLocation(
                "8d1714a7-f9e0-4f38-b5a2-dcc0e2834c08", "A27-U06", "SPBU Utara 2", 52, -245
            ),
        ),
        "condition": (
            ShopLocation(
                "4f1f6929-8ea1-4209-ab30-523b314efe11", "K40-U03", "Akademis.ai Motor", -16, -143
            ),
            ShopLocation(
                "78545bac-51dd-4898-bedc-33e33cc5820c", "L35-U01", "Bengkel motor Gotei", -64, -135
            ),
        ),
        "data": (
            ShopLocation(
                "a162273d-6832-4223-a2b9-409d6c291291", "O38-U06", "Akademis.ai Konter", -32, -106
            ),
            ShopLocation(
                "dffbbddb-37f7-4e2d-9d22-f91af809c2ab", "K36-U06", "TOPUP CELL", -46, -138
            ),
        ),
    },
    "kampung-sebelah": {
        "fuel": (
            ShopLocation(
                "914b6bb0-6684-4037-93bc-423810875eae", "A05-U06", "SPBU Kampung Sebelah", 33, 6
            ),
        ),
        "condition": (
            ShopLocation(
                "b2400595-7b5b-4571-aa2e-bcff27a04d9f", "A07-U06", "Bengke spesialis motor", 47, 6
            ),
        ),
        "data": (
            ShopLocation("bdda0310-4488-418f-a479-9710a10e2d96", "B09-U06", "Somadun Cell", 64, 14),
        ),
    },
    "pulau-seberang": {
        "fuel": (
            ShopLocation(
                "669fe6fc-6800-4731-a357-ef38d1a8f4fc", "F43-U01", "SPBU Pulau Seberang 2", 1026, 73
            ),
        ),
        "condition": (
            ShopLocation(
                "2191e03b-fa92-48f3-ad82-b74796b2096a", "A43-U06", "Ketok Magic Hihu", 1026, 17
            ),
        ),
        "data": (
            ShopLocation("9f5f66e8-7792-49f9-9349-67a9a27c3cca", "D43-U08", "abel cell", 1028, 41),
        ),
    },
}

COFFEE = NeedShop(
    "1ec63e49-4cee-4e78-8cfd-5feb8fab02ee", "K40-U09", "Akademis.ai Coffee", "coffee-shop"
)
ICAFE = NeedShop("8dcfc1b0-51f7-4bd2-8360-bf8402075698", "K39-U04", "Akademis.ai iCafe", "warnet")
ZIRAF = NeedShop(
    "e6c0481a-605e-4cff-bdd4-5bc6285a09a0", "H35-U03", "Akademis.ai - Ziraf Kopisop", "kedai-kopi"
)
GAMING_HOUSE = NeedShop(
    "36620a87-317d-40d9-b9eb-e7a372ef73df", "B37-U07", "Akademis.ai GamingHouse", "warnet"
)

NEED_SHOPS_BY_VILLAGE = {
    "desa-utara": {
        "makan": (
            NeedShop(
                "2df7cc17-29d4-4620-bad1-3602991f0dd5",
                "K40-U04",
                "Akademis.ai Restaurant",
                "restoran",
            ),
            NeedShop(
                "0495428a-7039-40b6-8837-166bafec0d6a",
                "K40-U08",
                "Akademis.ai Sembako",
                "warung-sembako",
            ),
            COFFEE,
            ICAFE,
        ),
        "kesehatan": (
            NeedShop(
                "cc73f5cd-2f05-4e9f-867e-19445c2065b3", "K40-U06", "Akademis.ai Farma", "toko-obat"
            ),
        ),
        "rekreasi": (COFFEE, ICAFE),
        "penampilan": (
            NeedShop(
                "f55d08f3-b0dd-46b9-83bd-b8fb46be542f",
                "K40-U07",
                "Akademis.ai Barbershop",
                "barbershop",
            ),
        ),
        "rumah": (
            NeedShop(
                "7c4c0d5f-dab6-435b-a958-3a85354647c4",
                "K40-U01",
                "Akademis.ai Bangunan",
                "toko-bangunan",
            ),
        ),
    },
    "kampung-sebelah": {
        "makan": (ZIRAF, GAMING_HOUSE),
        "kesehatan": (ZIRAF,),
        "rekreasi": (ZIRAF, GAMING_HOUSE),
    },
}

# Plot IDs from the captured directory. Resolve the current business before buying.
NEED_FALLBACK_PLOTS = {
    "desa-utara": {
        "makan": ("J23-U01", "restoran"),
        "kesehatan": ("N39-U07", "toko-obat"),
        "rekreasi": ("L38-U09", "coffee-shop"),
        "penampilan": ("L21-U09", "barbershop"),
        "rumah": ("L36-U09", "toko-bangunan"),
    },
    "kampung-sebelah": {
        "makan": ("D01-U09", "restoran"),
        "kesehatan": ("D02-U02", "toko-obat"),
        "rekreasi": ("A02-U04", "coffee-shop"),
    },
}
