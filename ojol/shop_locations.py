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

RESTAURANT = NeedShop(
    "2df7cc17-29d4-4620-bad1-3602991f0dd5", "K40-U04", "Akademis.ai Restaurant", "restoran"
)
JAJAN = NeedShop(
    "e42f8d13-2911-4d21-b499-e608f43dedaf", "K22-U10", "Akademis.ai Warung Jajan", "kios"
)
PECEL = NeedShop(
    "88b0c25a-1297-4c41-88b1-4c7df5e887e0", "O39-U01", "Akademis.ai Pecel Lele & Ayam", "lamongan"
)

NEED_SHOPS_BY_VILLAGE = {
    "desa-utara": {
        "makan": (
            RESTAURANT,
            NeedShop(
                "0495428a-7039-40b6-8837-166bafec0d6a",
                "K40-U08",
                "Akademis.ai Sembako",
                "warung-sembako",
            ),
            COFFEE,
            ICAFE,
            JAJAN,
            PECEL,
        ),
        "kesehatan": (
            NeedShop(
                "cc73f5cd-2f05-4e9f-867e-19445c2065b3", "K40-U06", "Akademis.ai Farma", "toko-obat"
            ),
        ),
        "rekreasi": (COFFEE, ICAFE, RESTAURANT, JAJAN, PECEL),
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

STUDY_FACILITIES_BY_VILLAGE = {
    "desa-utara": {
        "perpus": "90ae44da-6d71-495d-83f7-5b0b69400504",
        "kuliah": "0fb7ae51-34da-434e-a04f-050b0dd82f9b",
    },
    "kampung-sebelah": {
        "perpus": "2bc6a97e-82b9-48a1-8244-a37827ea6273",
        "kuliah": "8022c941-4160-4ac4-a124-35d3dda85798",
    },
}

BPJS_KANTOR_BY_VILLAGE = {
    "desa-utara": "5149bd70-4b0b-4b4e-be2e-839b7099f8dc",
    "kampung-sebelah": "592934a3-27b0-44ab-bb00-5c2cf53bfcb6",
    "pulau-seberang": "c9d1635a-a08b-4c33-9e0f-27bd50b17fd6",
}

HEALTH_FACILITIES_BY_VILLAGE = {
    "desa-utara": (
        "2ff500f4-fe31-438b-be99-801eb4e6b363",  # Puskesmas
        "dbc8fb79-43d3-4b75-b3ab-dac2d0c17b10",  # Rumah sakit desa
        "66c40451-aba1-4b58-92e3-e58a18e1e02a",  # Puskesmas
    ),
    "kampung-sebelah": (
        "c00b9433-b7a8-4ad9-874e-b4f50001723d",  # Puskesmas
        "c2b33dec-a385-4076-8733-5729a1ac3e5c",  # Rumah Sakit
        "0c04898c-20b1-434b-8c96-ebafef082aee",  # Puskesmas
    ),
    "pulau-seberang": (
        "48b978dd-c139-4ac6-a4d9-f178dd010882",  # Puskesmas
        "eaa4fb55-489c-4b81-9cbf-cd4b110d260f",  # Rumah sakit
    ),
}
