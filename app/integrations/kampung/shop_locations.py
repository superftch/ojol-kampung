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
            ShopLocation(
                "6b398e0e-989c-43b2-87fd-77b1073c2060", "K36-U04", "SPBU Dusun Barat Atas", -43, -143
            ),
            ShopLocation(
                "0ae0ecbe-5de8-44d0-b6c4-48ab28aece01", "P29-U01", "SPBU Desa Timur 2", 66, -103
            ),
            ShopLocation(
                "f9812d1c-a79e-45fd-a8e8-9e7da12c4cf4", "Q38-U03", "SPBU Selatan", -30, -84
            ),
            ShopLocation(
                "5ade7caf-4ab7-4202-b654-26e91ca621e0", "T32-U06", "SPBU Barat Atas", -85, -55
            ),
        ),
        "condition": (
            ShopLocation(
                "4f1f6929-8ea1-4209-ab30-523b314efe11", "K40-U03", "Akademis.ai Motor", -16, -143
            ),
            ShopLocation(
                "e6426342-2654-4bde-965e-a81fabf2fbea",
                "N22-U10",
                "Akademis.ai Abadi Bengkel",
                10,
                -125,
            ),
        ),
        "data": (
            ShopLocation(
                "a162273d-6832-4223-a2b9-409d6c291291", "O38-U06", "Akademis.ai Konter", -32, -106
            ),
        ),
    },
    "kampung-sebelah": {
        "fuel": (
            ShopLocation(
                "914b6bb0-6684-4037-93bc-423810875eae", "A05-U06", "SPBU Kampung Sebelah", 33, 6
            ),
            ShopLocation(
                "200571c1-9704-4db3-8c06-1f9acf0483f5", "B07-U03", "SPBU Kampung Sebelah", 49, 9
            ),
            ShopLocation(
                "ad11ccf0-f220-422f-b0ff-f2ce4da0c26d", "D02-U08", "BUMDes", 10, 30
            ),
            ShopLocation(
                "7a9b42eb-848a-4bb2-9691-2c693f27f663", "D03-U03", "SPBU Desa Barat", 17, 25
            ),
            ShopLocation(
                "056b88f5-a37c-42b6-9974-420426103ede", "E36-U09", "SPBU Barat", -42, 38
            ),
            ShopLocation(
                "1c7a061c-e2f8-4df4-9484-ab63a59a2543", "K03-U01", "SPBU Desa Timur", 99, 1
            ),
            ShopLocation(
                "4d548bce-dbef-4320-abdd-0c7645c4811f", "K07-U08", "SPBU Timur 3", 140, 6
            ),
            ShopLocation(
                "dcb24343-a861-4fe3-96d1-4ef5ae81278b", "O04-U03", "SPBU Timur", 108, 33
            ),
            ShopLocation(
                "593ceb28-51c6-427a-a56a-47975275b984", "Q07-U04", "SPBU Timur 2", 141, 60
            ),
        ),
        "condition": (
            ShopLocation(
                "ef34199c-27f1-43b5-8126-08d094fc5f7d",
                "B09-U08",
                "Akademis.ai - Shop and Drive",
                66,
                14,
            ),
            ShopLocation(
                "2d9fda82-8056-4fe7-9b60-259515212452", "F35-U01", "Akademis.ai - Motor", -63, 52
            ),
            ShopLocation(
                "369ad3f1-1f7c-4dcf-ad05-002f363b5f62",
                "H34-U05",
                "Akademis Moto Repair & Modif",
                -66,
                68,
            ),
        ),
        "data": (
            ShopLocation(
                "bdda0310-4488-418f-a479-9710a10e2d96", "B09-U06", "Akademis.ai Cell", 64, 14
            ),
            ShopLocation(
                "c6d3ae05-3260-44d8-8e8c-d399c91bcc7d",
                "I33-U07",
                "Akademis.ai Konter Pulsa",
                -76,
                81,
            ),
        ),
    },
    "pulau-seberang": {
        "fuel": (
            ShopLocation(
                "fc41f560-f96f-4a58-ab7a-d24ca9d23efb",
                "D44-U06",
                "SPBU Pulau Seberang 1",
                1033,
                41,
            ),
            ShopLocation(
                "669fe6fc-6800-4731-a357-ef38d1a8f4fc",
                "F43-U01",
                "SPBU Pulau Seberang 2",
                1026,
                73,
            ),
            ShopLocation(
                "a822f539-24cb-418d-b63e-7b24c78547bf",
                "H48-U01",
                "SPBU Pulau Seberang 3",
                1072,
                89,
            ),
            ShopLocation(
                "e9885d29-8139-4ff0-9363-7e43880c7fac",
                "C48-U04",
                "SPBU Pulau Seberang 4",
                1075,
                28,
            ),
        ),
        "condition": (),
        "data": (),
    },
}

COFFEE = NeedShop(
    "1ec63e49-4cee-4e78-8cfd-5feb8fab02ee", "K40-U09", "Akademis.ai Coffee", "coffee-shop"
)
COFFEE_UTARA_2 = NeedShop(
    "046aba3d-d08b-4375-b8dd-a2a1c84f5a3e", "D22-U09", "Akademis.ai - Coffee", "coffee-shop"
)
ICAFE = NeedShop("8dcfc1b0-51f7-4bd2-8360-bf8402075698", "K39-U04", "Akademis.ai iCafe", "warnet")
ZIRAF = NeedShop(
    "e6c0481a-605e-4cff-bdd4-5bc6285a09a0", "H35-U03", "Akademis.ai - Ziraf Kopisop", "kedai-kopi"
)
GAMING_HOUSE = NeedShop(
    "36620a87-317d-40d9-b9eb-e7a372ef73df", "B37-U07", "Akademis.ai GamingHouse", "warnet"
)
KIOS_MAKANAN = NeedShop(
    "30ace818-fe94-48cc-9435-6a714285d28a", "B01-U04", "Akademis.ai - Kios Makanan", "kios"
)
WARUNG_MADURA = NeedShop(
    "9738447d-db7c-4147-9f75-edd86c9997f6", "T06-U01", "Akademis.ai - Warung Madura", "kios"
)
RUMAH_MAKAN = NeedShop(
    "d05d9a65-d358-40b3-8920-d6b128d632f4",
    "G05-U07",
    "Rumah Makan - Akademis.ai",
    "rumah-makan",
)

RESTAURANT = NeedShop(
    "2df7cc17-29d4-4620-bad1-3602991f0dd5", "K40-U04", "Akademis.ai Restaurant", "restoran"
)
WARUNG_UTARA = NeedShop(
    "274cfbcc-16e2-4d4a-a714-d78b7fa51a3a",
    "E29-U05",
    "Akademis.ai - Warung",
    "warung-sembako",
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
            WARUNG_UTARA,
            COFFEE,
            COFFEE_UTARA_2,
            ICAFE,
            JAJAN,
            PECEL,
        ),
        "kesehatan": (
            NeedShop(
                "cc73f5cd-2f05-4e9f-867e-19445c2065b3", "K40-U06", "Akademis.ai Farma", "toko-obat"
            ),
        ),
        "rekreasi": (COFFEE, COFFEE_UTARA_2, ICAFE, RESTAURANT, JAJAN, PECEL, WARUNG_UTARA),
        "penampilan": (
            NeedShop(
                "f55d08f3-b0dd-46b9-83bd-b8fb46be542f",
                "K40-U07",
                "Akademis.ai Barbershop",
                "barbershop",
            ),
            NeedShop(
                "18fc7ea7-bf68-4eb5-a9e0-f3c434323e4d",
                "I25-U01",
                "Akademis.ai - Barbershop",
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
        "makan": (ZIRAF, GAMING_HOUSE, KIOS_MAKANAN, WARUNG_MADURA, RUMAH_MAKAN),
        "kesehatan": (ZIRAF,),
        "rekreasi": (ZIRAF, GAMING_HOUSE, KIOS_MAKANAN, WARUNG_MADURA, RUMAH_MAKAN),
        "penampilan": (
            NeedShop(
                "beca69c4-7bd2-4624-8a97-150654d28914",
                "C37-U02",
                "Akademis.ai - Pangkas Rambut",
                "barbershop",
            ),
        ),
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
