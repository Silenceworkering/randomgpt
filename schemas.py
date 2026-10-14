from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .catalog import ITEMS, CATEGORIES

Category = Literal["cpu", "gpu", "motherboard", "ram", "ssd", "psu", "case", "cooler"]
Purpose = Literal["gaming", "work", "office"]


class Prices(BaseModel):
    model_config = ConfigDict(extra="forbid")
    price_overrides: dict[str, Annotated[int, Field(strict=True)]] = Field(
        default_factory=dict, max_length=100
    )

    @model_validator(mode="after")
    def valid_prices(self):
        for key, price in self.price_overrides.items():
            if (
                key not in ITEMS
                or isinstance(price, bool)
                or not 1 <= price <= 2_000_000
            ):
                raise ValueError(
                    "Цена должна быть от 1 до 2 000 000 ₽ для модели из каталога."
                )
        return self


class BuildRequest(Prices):
    components: dict[Category, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_parts(self):
        for category, item_id in self.components.items():
            if item_id not in ITEMS or ITEMS[item_id]["category"] != category:
                raise ValueError(
                    f"Неизвестная модель или неверная категория: {category}."
                )
        return self


class RecommendRequest(Prices):
    budget: int = Field(ge=15_000, le=500_000, strict=True)
    purpose: Purpose = "gaming"
    cpu_brand: Literal["any", "AMD", "Intel"] = "any"
    gpu_brand: Literal["any", "AMD", "NVIDIA"] = "any"


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def valid_ids(self):
        if len(set(self.ids)) != len(self.ids) or any(i not in ITEMS for i in self.ids):
            raise ValueError("Выберите от 2 до 4 разных моделей каталога.")
        if len({ITEMS[i]["category"] for i in self.ids}) != 1:
            raise ValueError("Можно сравнивать только модели одной категории.")
        return self
