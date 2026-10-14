"""Deterministic, free search shared by HTTP API and Telegram. No AI API."""

import math
from itertools import product
from .catalog import ITEMS, GROUPS, CATEGORIES, public_item
from .schemas import BuildRequest, RecommendRequest


class NoBuildError(ValueError):
    pass


def price(item, overrides):
    return overrides.get(item["id"], item["estimate_rub"])


def compatibility(parts: dict[str, dict]) -> dict:
    errors, warnings, checks = [], [], []

    def check(key, ready, condition, ok, bad):
        status = "pending" if not ready else ("ok" if condition else "error")
        message = (
            "Добавьте компоненты для проверки."
            if not ready
            else (ok if condition else bad)
        )
        checks.append({"key": key, "status": status, "message": message})
        if status == "error":
            errors.append(message)

    s = {k: v["specs"] for k, v in parts.items()}
    c, b, r, g, p, box, cool = (
        s.get(k, {})
        for k in ["cpu", "motherboard", "ram", "gpu", "psu", "case", "cooler"]
    )
    check(
        "socket",
        c and b,
        c.get("socket") == b.get("socket"),
        "Сокет процессора и платы совпадает.",
        "Сокеты процессора и платы не совпадают.",
    )
    check(
        "cpu_support",
        c and b,
        parts.get("cpu", {}).get("id") in b.get("supported_cpus", []),
        "Процессор есть в списке поддерживаемых моделей каталога.",
        "Плата не поддерживает этот процессор по данным каталога.",
    )
    check(
        "ram",
        c and b and r,
        r.get("memory_type") == b.get("memory_type")
        and r.get("memory_type") in c.get("memory_types", [])
        and r.get("modules", 0) <= b.get("ram_slots", 0)
        and r.get("capacity_gb", 0) <= b.get("max_ram_gb", 0),
        "Тип и объём памяти подходят процессору и плате.",
        "Тип, объём или число модулей памяти несовместимы.",
    )
    check(
        "board_case",
        b and box,
        b.get("form_factor") in box.get("board_forms", []),
        "Материнская плата помещается в корпус.",
        "Корпус не поддерживает форм-фактор платы.",
    )
    integrated = bool(c and c.get("igpu") and not g)
    check(
        "gpu_case",
        (g and box) or (integrated and box),
        g.get("length_mm", 0) <= box.get("max_gpu_mm", 0)
        and g.get("width_slots", 0) <= box.get("max_gpu_slots", 0),
        (
            "Используется встроенная графика: отдельная видеокарта не нужна."
            if integrated
            else "Видеокарта помещается в корпус по длине и слотам."
        ),
        "Видеокарта не помещается в корпус.",
    )
    check(
        "cooler_cpu",
        cool and c,
        c.get("socket") in cool.get("sockets", [])
        and cool.get("thermal_budget_w", 0) >= c.get("power_w", 0),
        "Крепление и расчётный тепловой запас кулера подходят.",
        "Кулер не поддерживает сокет или имеет недостаточный тепловой запас.",
    )
    check(
        "cooler_case",
        cool and box,
        cool.get("height_mm", 0) <= box.get("max_cooler_mm", 0),
        "Кулер помещается в корпус по высоте.",
        "Кулер слишком высокий для корпуса.",
    )
    consumption = c.get("power_w", 0) + g.get("power_w", 0) + 60
    required = math.ceil(consumption * 1.35 / 50) * 50
    check(
        "power",
        c and p,
        p.get("wattage", 0) >= required,
        f"Блок питания покрывает расчёт с запасом: {required} Вт.",
        f"Недостаточная мощность БП: нужно не менее {required} Вт.",
    )
    check(
        "connectors",
        (g and p) or (integrated and p),
        p.get("pcie_8pin", 0) >= g.get("pcie_8pin", 0),
        (
            "Встроенной графике отдельное питание не нужно."
            if integrated
            else "Разъёмов PCIe 8-pin достаточно."
        ),
        "Недостаточно разъёмов питания видеокарты.",
    )
    check(
        "psu_case",
        p and box,
        p.get("form_factor") == box.get("psu_form")
        and p.get("length_mm", 0) <= box.get("max_psu_mm", 0),
        "Блок питания помещается в корпус.",
        "Блок питания не подходит корпусу.",
    )
    check(
        "ssd",
        b and s.get("ssd"),
        b.get("m2_nvme", False),
        "Плата поддерживает выбранный M.2 NVMe SSD.",
        "Плата не поддерживает выбранный SSD.",
    )
    check(
        "display",
        c,
        bool(g) or c.get("igpu", False),
        "Есть дискретная или встроенная графика.",
        "У процессора нет встроенной графики: добавьте видеокарту.",
    )
    required_categories = [k for k in CATEGORIES if k != "gpu"]
    missing = [CATEGORIES[k] for k in required_categories if k not in parts]
    if b.get("bios_note"):
        warnings.append(b["bios_note"])
    if r and b and not errors:
        warnings.append(
            "Частоты XMP/EXPO не гарантированы: проверьте QVL и настройки BIOS."
        )
    if cool:
        warnings.append(
            "Проверьте комплект крепления и зазор между кулером и модулями памяти."
        )
    return {
        "compatible": not errors,
        "complete": not missing and (bool(g) or bool(c.get("igpu"))),
        "errors": errors,
        "warnings": warnings,
        "missing": missing,
        "checks": checks,
        "estimated_power_w": consumption if c else None,
        "recommended_psu_w": required if c else None,
    }


def evaluate(request: BuildRequest) -> dict:
    parts = {k: ITEMS[v] for k, v in request.components.items()}
    return {
        "components": {
            k: {
                **public_item(v),
                "calculation_rub": price(v, request.price_overrides),
                "user_price": v["id"] in request.price_overrides,
            }
            for k, v in parts.items()
        },
        "total_rub": sum(price(v, request.price_overrides) for v in parts.values()),
        "price_kind": "mixed" if request.price_overrides else "estimate",
        "compatibility": compatibility(parts),
    }


def utility(c, g, ram, ssd, purpose):
    """Relative weights, not FPS. Diminishing returns for RAM and SSD."""
    cpu, gpu = c["specs"]["score"], (
        g["specs"]["score"] if g else c["specs"].get("igpu_score", 0)
    )
    memory = min(ram["specs"]["capacity_gb"], 32) / 16
    storage = min(ssd["specs"]["capacity_gb"], 2000) / 1000
    if purpose == "gaming":
        return (
            0.30 * cpu
            + 0.65 * gpu
            + 4 * memory
            + 2 * storage
            - max(0, gpu - 1.8 * cpu) * 0.15
        )
    if purpose == "work":
        return 0.65 * cpu + 0.20 * gpu + 12 * memory + 5 * storage
    return min(cpu, 65) * 0.5 + min(gpu, 12) * 0.1 + 9 * memory + 5 * storage


def recommend(req: RecommendRequest) -> dict:
    cpus = [
        c
        for c in GROUPS["cpu"]
        if req.cpu_brand == "any" or c["brand"] == req.cpu_brand
    ]
    gpus = [
        g
        for g in GROUPS["gpu"]
        if req.gpu_brand == "any" or g["brand"] == req.gpu_brand
    ]
    # Gaming always gets a discrete card; integrated graphics allowed for office/work
    # only when no discrete GPU brand has been requested.
    if req.purpose != "gaming" and req.gpu_brand == "any":
        gpus = [None] + gpus
    best, best_key, minimum = None, None, None
    prices = req.price_overrides
    for cpu, board, ram in product(cpus, GROUPS["motherboard"], GROUPS["ram"]):
        if (
            cpu["id"] not in board["specs"]["supported_cpus"]
            or ram["specs"]["memory_type"] != board["specs"]["memory_type"]
        ):
            continue
        for gpu in gpus:
            if gpu is None and not cpu["specs"]["igpu"]:
                continue
            base = {"cpu": cpu, "motherboard": board, "ram": ram}
            if gpu:
                base["gpu"] = gpu
            # Auxiliary parts provide no artificial score bonus: pick cheapest valid trio.
            aux = None
            for cooler, case, psu in product(
                GROUPS["cooler"], GROUPS["case"], GROUPS["psu"]
            ):
                cost = sum(price(i, prices) for i in [cooler, case, psu])
                if aux and cost >= aux[0]:
                    continue
                candidate = {**base, "cooler": cooler, "case": case, "psu": psu}
                if compatibility(candidate)["compatible"]:
                    aux = (cost, candidate)
            if not aux:
                continue
            for ssd in GROUPS["ssd"]:
                parts = {**aux[1], "ssd": ssd}
                total = sum(price(i, prices) for i in parts.values())
                minimum = total if minimum is None else min(total, minimum)
                if total > req.budget:
                    continue
                score = utility(cpu, gpu, ram, ssd, req.purpose)
                # Highest task utility, cheaper build resolves equal-score ties.
                key = (round(score, 6), -total)
                if best_key is None or key > best_key:
                    best_key, best = key, parts
    if best is None:
        suffix = (
            f" Минимальная расчётная сумма с этими предпочтениями: {minimum:,} ₽.".replace(
                ",", " "
            )
            if minimum
            else ""
        )
        raise NoBuildError(
            "Не удалось подобрать полный совместимый ПК в пределах бюджета."
            + suffix
            + " Увеличьте бюджет или измените предпочтения."
        )
    result = evaluate(
        BuildRequest(
            components={k: v["id"] for k, v in best.items()}, price_overrides=prices
        )
    )
    result.update(
        budget=req.budget,
        remaining_rub=req.budget - result["total_rub"],
        purpose=req.purpose,
        score=round(best_key[0], 2),
        explanation=[
            "Все выбранные компоненты прошли доступные проверки совместимости.",
            {
                "gaming": "Приоритет видеокарте и балансу с процессором.",
                "work": "Приоритет процессору, памяти и накопителю. Для специфичных задач проверьте требования ПО.",
                "office": "Приоритет достаточной производительности, памяти и SSD; встроенная графика допустима.",
            }[req.purpose],
            "Выбрана наибольшая оценка для задачи в пределах бюджета; при равной оценке — меньшая цена.",
            "Оценка относительная: не прогноз FPS. Периферия, ОС и доставка в бюджет не входят.",
        ],
    )
    return result
