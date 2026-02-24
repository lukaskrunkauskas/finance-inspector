from enum import Enum


class CategoryEnum(Enum):
    SHOPPING = ("Shopping", "#134E8E")
    FOOD = ("Food & Dining", "#FFB33F")
    TRANSPORT = ("Transport", "#FF4400")
    HEALTH = ("Health", "#C00707")
    ENTERTAINMENT = ("Entertainment", "#237227")
    UTILITIES = ("Utilities", "#8A7650")
    EDUCATION = ("Education", "#EB4C4C")
    TRAVEL = ("Travel", "#F1FF5E")
    SAVINGS = ("Savings", "#B500B2")
    OTHER = ("Other", "#F2E3BB")

    def __init__(self, label: str, color: str):
        self.label = label
        self.color = color
