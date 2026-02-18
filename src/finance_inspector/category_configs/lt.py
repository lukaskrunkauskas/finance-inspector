from __future__ import annotations

from finance_inspector.models.enums.category_enum import CategoryEnum

# Lithuanian keywords — covers major local chains + global services common in LT
LT_CONFIG: dict[CategoryEnum, list[str]] = {
    CategoryEnum.SHOPPING: [
        "maxima", "rimi", "lidl", "iki", "norfa", "senukai", "ermitazas",
        "pigu.lt", "varle.lt", "amazon", "ebay", "zara", "h&m", "ikea",
        "aliexpress", "asos", "pepco",
    ],
    CategoryEnum.FOOD: [
        "mcdonalds", "kfc", "hesburger", "subway", "burger king", "starbucks",
        "wolt", "bolt food", "čili pica", "pizza jazz", "domino",
        "sushi", "kavine", "restoranas", "valgykla", "picerija",
    ],
    CategoryEnum.TRANSPORT: [
        "bolt", "uber", "trafi", "ltg link", "lux express",
        "circle k", "orlen", "neste", "viada",
        "parking", "autoplius", "lietuvos gelezinkeliai",
    ],
    CategoryEnum.HEALTH: [
        "eurovaistine", "benu vaistine", "camelia", "gintarine vaistine",
        "santara", "odontologas", "klinika", "gym", "fitakas",
        "lsmu", "kksc", "be healthy",
    ],
    CategoryEnum.ENTERTAINMENT: [
        "apollo", "forum cinemas", "multikino",
        "netflix", "spotify", "apple music", "disney", "hbo",
        "steam", "gaming", "telia play",
    ],
    CategoryEnum.UTILITIES: [
        "telia", "bite", "tele2", "init", "cgates",
        "ignitis", "enefit", "vatesi", "vilniaus energija",
        "draudimas", "ergo", "gjensidige", "lietuvos draudimas", "swed",
    ],
    CategoryEnum.EDUCATION: [
        "udemy", "coursera", "vu", "ktu", "vgtu", "lsmu", "mru",
        "mokykla", "kolegija", "universitetas", "knygos", "vaga",
    ],
    CategoryEnum.TRAVEL: [
        "airbnb", "booking.com", "hotels.com", "expedia",
        "ryanair", "airbaltic", "wizz air", "norwegian", "lot",
        "viešbutis", "hostel", "pansionas",
    ],
    CategoryEnum.SAVINGS: [
        "savings", "investicijos", "paysera", "revolut savings",
        "swedbank invest", "luminor", "siauliu bankas", "crypto",
    ],
    CategoryEnum.OTHER: [],
}
