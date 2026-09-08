"""Static English vocabulary and patterns used by the DLP rule engine."""

import re


INGREDIENT_TERMS = {
    "basil",
    "butter",
    "cheese",
    "dough",
    "flour",
    "garlic",
    "mozzarella",
    "oil",
    "olive oil",
    "olive",
    "olives",
    "oregano",
    "pepperoni",
    "salt",
    "sauce",
    "sugar",
    "tomato",
    "tomatoes",
    "water",
    "yeast",
}

INGREDIENT_ALIASES = {
    "olives": "olive",
    "tomatoes": "tomato",
}

ACTION_TERMS = {
    "add",
    "bake",
    "baking",
    "combine",
    "divide",
    "ferment",
    "knead",
    "kneading",
    "mix",
    "mixing",
    "preheat",
    "proof",
    "rest",
    "roll",
    "rolling",
    "shape",
    "spread",
    "stir",
    "stirring",
}

SEQUENCE_TERMS = {"after that", "first step", "next", "second step", "then"}

SENSITIVE_TERM_SCORES = {
    "confidential": 3,
    "formula": 3,
    "recipe": 3,
    "secret": 1,
}

RECIPE_FRAGMENT_FILLER_TERMS = {
    "a",
    "an",
    "and",
    "for",
    "into",
    "it",
    "of",
    "some",
    "the",
    "them",
    "then",
    "to",
    "with",
}

QUANTITY_PATTERN = re.compile(
    r"\b(?:\d+(?:[.,]\d+)?|an?)\s*"
    r"(?:grams?|g|kilograms?|kg|cups?|tablespoons?|tbsp|teaspoons?|tsp|"
    r"milliliters?|ml|ounces?|oz|pounds?|lb|pinch(?:es)?)\b"
)

TEMPERATURE_OR_TIME_PATTERN = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:degrees?|°[cf]?|minutes?|hours?)\b"
)
