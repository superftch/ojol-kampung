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

FOOD_SHOPS = {
    "coffee-shop",
    "kedai-kopi",
    "kios",
    "lamongan",
    "minimarket",
    "restoran",
    "rumah-makan",
    "warung",
    "warung-sembako",
    "warnet",
}
NEED_SHOP_CATEGORIES = {
    "makan": FOOD_SHOPS,
    "kesehatan": FOOD_SHOPS | {"toko-obat"},
    "rekreasi": FOOD_SHOPS,
    "penampilan": {"barbershop"},
    "rumah": {"toko-bangunan"},
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

GYM_FACILITIES_BY_VILLAGE = {
    "desa-utara": (
        "296dc278-b765-4caf-9349-469385d6fc03",  # Gym desa 2
        "d645f8b3-b82f-4172-ba39-7b5f116dd6ba",  # Gym desa
    ),
    "kampung-sebelah": (),
    "pulau-seberang": (),
}

SPPG_FACILITIES_BY_VILLAGE = {
    "desa-utara": (
        "04f36c8b-f2a6-4d24-945c-a0b62540cb56",
        "a8d496e4-9d2d-46b8-860a-a54ea73d253d",
    ),
    "kampung-sebelah": (
        "c30281d2-de01-4fdc-a7a2-20aa039112a0",
        "e21259ea-3a4e-4d16-8287-dbb1d989e6bf",
        "f4b29614-e075-4af6-9962-f37853e71958",
    ),
    "pulau-seberang": ("a2c2d43b-d560-4a0d-a393-aa6ae71877b9",),
}

RECREATION_FACILITIES_BY_VILLAGE = {
    "desa-utara": (
        "763067a5-755d-4b76-8ce8-1049f895bbe7",  # Alun-alun
        "c7927aee-ef62-4552-8666-1f564c0300b4",  # Alun-alun
        "9ba191a6-5803-48b7-87a8-f0397b800ca7",  # Taman desa
        "37e255ac-1c00-4755-9a27-1a9967a2534f",  # Taman desa
        "2c7bcbc1-c55e-4e43-bbb5-ca1a5993f8b6",  # Taman desa
    ),
    "kampung-sebelah": (
        "62106435-e70f-4ac2-9514-c3be0c0057e0",  # Alun-alun
        "a1fee99c-4812-49dd-b02a-8c4be0b3f855",  # Alun-alun
        "dc0d53d2-7b96-49cc-b174-6feadeee1cc7",  # Alun-alun
        "e16c7ea8-aabe-436e-b7cf-3c39fd3fd104",  # Taman hijau
        "975d3496-1e13-4413-b7e1-6033922f115c",  # Taman desa
        "14d8dc53-f28a-466a-81ab-2e612f744917",  # Taman desa
    ),
    "pulau-seberang": (
        "bd9cf9f9-2789-4e29-acc4-e7fb0e0e8ca3",  # Alun-alun desa seberang
        "1919456a-3011-43df-8e5a-7242ef4bb2c3",  # Taman desa
        "020e81d0-dcbb-46c3-ab5a-ef58c33c5942",  # Taman desa 16
    ),
}
