from __future__ import annotations

from finance_inspector.models.enums.category_enum import CategoryEnum

# English / generic Revolut keywords
BASE_CONFIG: dict[CategoryEnum, list[str]] = {
    CategoryEnum.SHOPPING: [
        "amazon", "ebay", "zara", "h&m", "ikea", "primark", "asos", "aliexpress",
    ],
    CategoryEnum.FOOD: [
        "mcdonalds", "kfc", "subway", "burger king", "starbucks", "costa",
        "deliveroo", "uber eats", "wolt", "just eat", "pizza hut",
    ],
    CategoryEnum.TRANSPORT: [
        "uber", "bolt", "taxi", "bus", "train", "metro", "tram",
        "fuel", "petrol", "parking", "ryanair", "easyjet",
    ],
    CategoryEnum.HEALTH: [
        "pharmacy", "chemist", "doctor", "hospital", "clinic", "dentist",
        "gym", "fitness", "optician",
    ],
    CategoryEnum.ENTERTAINMENT: [
        "netflix", "spotify", "apple music", "disney", "hbo", "steam",
        "cinema", "theatre", "concert", "gaming",
    ],
    CategoryEnum.UTILITIES: [
        "electric", "electricity", "water", "gas", "internet", "broadband",
        "phone", "mobile", "insurance", "council tax",
    ],
    CategoryEnum.EDUCATION: [
        "udemy", "coursera", "skillshare", "school", "university",
        "college", "tuition", "books", "kindle",
    ],
    CategoryEnum.TRAVEL: [
        "airbnb", "booking.com", "hotels.com", "expedia", "hotel",
        "hostel", "airbaltic", "wizz air", "norwegian",
    ],
    CategoryEnum.SAVINGS: [
        "savings", "investment", "trading", "crypto", "pension",
    ],
    CategoryEnum.OTHER: [],
}
