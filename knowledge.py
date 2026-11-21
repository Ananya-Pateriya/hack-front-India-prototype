"""Static knowledge for FrostMind: shelf life, aliases, noise filters, tips.

Shelf-life values are deliberately conservative refrigerated-storage estimates
for a demo. They are NOT copied from a reference. Verify against the USDA
FoodKeeper open dataset (FoodSafety.gov/FoodKeeper, also on Data.gov) or FSSAI
guidance before any real-world use.
"""

EXPIRY_ALERT_DAYS = 3
MEALS = ("Breakfast", "Lunch", "Dinner")

# Days of safe refrigerated life after purchase.
SHELF_LIFE_DB = {
    "milk": 7, "bread": 4, "eggs": 21, "yogurt": 10, "butter": 30,
    "cheese": 21, "paneer": 5, "cream": 7, "juice": 5,
    "tomatoes": 5, "apples": 14, "bananas": 4, "spinach": 3, "coriander": 4,
    "carrots": 14, "onions": 30, "potatoes": 21, "mushroom": 4,
    "capsicum": 7, "cauliflower": 7, "cabbage": 10, "cucumber": 5,
    "lemon": 14, "ginger": 14, "garlic": 30, "peas": 4, "okra": 3,
    "brinjal": 5, "beans": 5, "chicken": 2, "fish": 1, "mutton": 2,
}

# Regional / informal names -> canonical key in SHELF_LIFE_DB.
ALIASES = {
    "dahi": "yogurt", "curd": "yogurt", "doodh": "milk", "toned": "milk",
    "pav": "bread", "anda": "eggs", "egg": "eggs", "makhan": "butter",
    "malai": "cream", "tamatar": "tomatoes", "tomato": "tomatoes",
    "seb": "apples", "apple": "apples", "banana": "bananas",
    "palak": "spinach", "dhania": "coriander", "gajar": "carrots",
    "carrot": "carrots", "pyaz": "onions", "onion": "onions",
    "aloo": "potatoes", "potato": "potatoes", "mushrooms": "mushroom",
    "shimla": "capsicum", "nimbu": "lemon", "lemons": "lemon",
    "adrak": "ginger", "lehsun": "garlic", "matar": "peas", "mutter": "peas",
    "bhindi": "okra", "baingan": "brinjal", "eggplant": "brinjal",
    "murgh": "chicken", "gosht": "mutton",
}

# Receipt noise that must never be matched to food.
STOPWORDS = {
    "mrp", "rs", "inr", "qty", "pc", "pcs", "pkt", "pack", "packet", "pouch",
    "tray", "box", "bottle", "jar", "g", "gm", "gms", "kg", "ml", "l", "ltr",
    "litre", "liter", "total", "gst", "cgst", "sgst", "bill", "invoice",
    "cash", "card", "upi", "change", "amt", "amount", "discount", "item",
    "items", "fresh", "farm", "premium", "special", "offer", "new", "pure",
    "of", "whole", "brown", "white", "large", "loose", "organic",
    "amul", "britannia", "mother", "dairy", "nestle", "tata", "patanjali",
    "ashirvaad", "aashirvaad", "nandini", "maggi", "lays", "cadbury",
    "parle", "haldiram", "everest", "mdh",
}

# If any of these appear on the line it is a packaged/processed product, not
# fresh stock: "PEANUT BUTTER", "TOMATO KETCHUP", "ICE CREAM", "DOSA BATTER".
NEGATIVE_WORDS = {
    "ketchup", "sauce", "chips", "chocolate", "chocolates", "cocoa", "ice",
    "peanut", "powder", "biscuit", "biscuits", "cookie", "cookies", "wafer",
    "wafers", "namkeen", "pickle", "jam", "squash", "syrup", "candy", "cake",
    "noodles", "masala", "oil", "soap", "shampoo", "detergent", "batter",
    "coconut", "mix", "puree", "paste",
}

# Rule-based "use it up" ideas. No model, no network. No safety numbers.
RESCUE_IDEAS = {
    "milk": "Set it as curd overnight or boil it into kheer.",
    "bread": "Cube and bake into croutons, or make bread upma.",
    "eggs": "Hard-boil a batch today for easy snacks.",
    "yogurt": "Whisk into lassi or use it as a marinade.",
    "tomatoes": "Cook into a base gravy and freeze it.",
    "paneer": "Pan-fry for a quick bhurji or tikka tonight.",
    "spinach": "Blanch and freeze, or make palak dal tonight.",
    "coriander": "Blitz into green chutney with chilli and lemon.",
    "bananas": "Freeze peeled for smoothies, or bake banana bread.",
    "chicken": "Cook it today and refrigerate leftovers promptly.",
    "mutton": "Cook it today and refrigerate leftovers promptly.",
    "fish": "Cook it today. Fish does not wait.",
    "mushroom": "Saute with garlic, or add to tonight's pulao.",
    "capsicum": "Slice and stir-fry, or add to a wrap.",
    "cauliflower": "Roast it or make aloo gobi tonight.",
    "cabbage": "Shred into a quick sabzi or slaw.",
    "cucumber": "Make raita or a quick salad.",
    "cheese": "Melt into a toastie or grate over pasta.",
    "peas": "Make matar paneer or freeze the rest.",
    "okra": "Stir-fry bhindi tonight.",
    "brinjal": "Roast for baingan bharta.",
    "beans": "Stir-fry or add to dal.",
}

ITEM_EMOJI = {
    "milk": "🥛", "bread": "🍞", "eggs": "🥚", "yogurt": "🥣", "butter": "🧈",
    "cheese": "🧀", "paneer": "🧀", "cream": "🥛", "juice": "🧃",
    "tomatoes": "🍅", "apples": "🍎", "bananas": "🍌", "spinach": "🥬",
    "coriander": "🌿", "carrots": "🥕", "onions": "🧅", "potatoes": "🥔",
    "mushroom": "🍄", "capsicum": "🫑", "cauliflower": "🥦", "cabbage": "🥬",
    "cucumber": "🥒", "lemon": "🍋", "ginger": "🫚", "garlic": "🧄",
    "peas": "🫛", "okra": "🌱", "brinjal": "🍆", "beans": "🫘",
    "chicken": "🍗", "fish": "🐟", "mutton": "🍖",
}