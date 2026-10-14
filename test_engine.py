from copy import deepcopy
from itertools import product
import pytest
from pydantic import ValidationError
from app.catalog import ITEMS, GROUPS
from app.engine import compatibility, recommend, evaluate, utility, NoBuildError
from app.schemas import BuildRequest, RecommendRequest, CompareRequest

BASE = {
    "cpu": "r5600",
    "motherboard": "b550",
    "ram": "ddr4-16",
    "gpu": "rtx4060",
    "ssd": "sn580-1",
    "psu": "pk550",
    "case": "matrexx40",
    "cooler": "ag200",
}


def parts():
    return {k: deepcopy(ITEMS[v]) for k, v in BASE.items()}


def test_valid_complete_build():
    check = compatibility(parts())
    assert check["compatible"] and check["complete"]
    assert check["recommended_psu_w"] == 400
    assert len(check["checks"]) == 12


@pytest.mark.parametrize(
    "category,field,value,check_key",
    [
        ("cpu", "socket", "LGA1700", "socket"),
        ("motherboard", "supported_cpus", [], "cpu_support"),
        ("ram", "memory_type", "DDR5", "ram"),
        ("ram", "modules", 8, "ram"),
        ("ram", "capacity_gb", 256, "ram"),
        ("case", "board_forms", ["ITX"], "board_case"),
        ("gpu", "length_mm", 500, "gpu_case"),
        ("gpu", "width_slots", 7, "gpu_case"),
        ("cooler", "sockets", ["LGA1700"], "cooler_cpu"),
        ("cooler", "thermal_budget_w", 20, "cooler_cpu"),
        ("cooler", "height_mm", 200, "cooler_case"),
        ("psu", "wattage", 200, "power"),
        ("psu", "pcie_8pin", 0, "connectors"),
        ("psu", "length_mm", 200, "psu_case"),
        ("psu", "form_factor", "SFX", "psu_case"),
        ("motherboard", "m2_nvme", False, "ssd"),
    ],
)
def test_incompatibilities(category, field, value, check_key):
    build = parts()
    build[category]["specs"][field] = value
    result = compatibility(build)
    assert not result["compatible"]
    assert (
        next(c for c in result["checks"] if c["key"] == check_key)["status"] == "error"
    )


def test_no_gpu_requires_integrated_graphics():
    build = parts()
    del build["gpu"]
    assert not compatibility(build)["compatible"]
    build["cpu"] = ITEMS["r5600g"]
    assert compatibility(build)["compatible"] and compatibility(build)["complete"]


def test_partial_build_is_not_complete():
    check = compatibility({})
    assert check["compatible"] and not check["complete"] and len(check["missing"]) == 7


@pytest.mark.parametrize(
    "purpose,budget,cpu_brand,gpu_brand",
    [
        ("gaming", 80000, "any", "any"),
        ("gaming", 120000, "AMD", "NVIDIA"),
        ("gaming", 120000, "Intel", "AMD"),
        ("work", 110000, "any", "any"),
        ("office", 45000, "any", "any"),
        ("office", 65000, "Intel", "any"),
        ("work", 140000, "AMD", "AMD"),
    ],
)
def test_recommendation_invariants(purpose, budget, cpu_brand, gpu_brand):
    req = RecommendRequest(
        budget=budget, purpose=purpose, cpu_brand=cpu_brand, gpu_brand=gpu_brand
    )
    result = recommend(req)
    assert result["total_rub"] <= budget
    assert result["compatibility"]["compatible"] and result["compatibility"]["complete"]
    assert (
        sum(i["calculation_rub"] for i in result["components"].values())
        == result["total_rub"]
    )
    if cpu_brand != "any":
        assert result["components"]["cpu"]["brand"] == cpu_brand
    if gpu_brand != "any":
        assert result["components"]["gpu"]["brand"] == gpu_brand
    if purpose == "gaming":
        assert "gpu" in result["components"]
    assert recommend(req) == result


def test_impossible_budget_has_explanation():
    with pytest.raises(NoBuildError, match="Минимальная расчётная сумма"):
        recommend(RecommendRequest(budget=15000, purpose="gaming"))


def test_user_price_changes_calculation():
    checked = evaluate(BuildRequest(components=BASE, price_overrides={"r5600": 100}))
    assert checked["components"]["cpu"]["calculation_rub"] == 100
    assert (
        checked["total_rub"]
        == sum(ITEMS[id]["estimate_rub"] for id in BASE.values()) - 10400
    )
    expensive = {i["id"]: 2000000 for i in GROUPS["gpu"]}
    with pytest.raises(NoBuildError):
        recommend(RecommendRequest(budget=100000, price_overrides=expensive))


@pytest.mark.parametrize(
    "payload",
    [
        {"budget": 14999},
        {"budget": 500001},
        {"budget": True},
        {"budget": "80000"},
        {"budget": 80000, "purpose": "unknown"},
        {"budget": 80000, "cpu_brand": "NVIDIA"},
        {"budget": 80000, "price_overrides": {"unknown": 10}},
        {"budget": 80000, "price_overrides": {"r5600": 0}},
        {"budget": 80000, "price_overrides": {"r5600": True}},
        {"budget": 80000, "price_overrides": {"r5600": 1.5}},
        {"budget": 80000, "extra": "invalid"},
    ],
)
def test_invalid_recommendation_input(payload):
    with pytest.raises(ValidationError):
        RecommendRequest(**payload)


@pytest.mark.parametrize(
    "ids", [["r5600"], ["r5600", "r5600"], ["r5600", "rx6600"], ["unknown", "r5600"]]
)
def test_comparison_validation(ids):
    with pytest.raises(ValidationError):
        CompareRequest(ids=ids)


def test_invalid_category_assignment():
    with pytest.raises(ValidationError):
        BuildRequest(components={"cpu": "rtx4060"})


def test_optimum_matches_exhaustive_reference(monkeypatch):
    # Independent complete-build enumeration on a bounded inventory.
    subset = {
        "cpu": ["r5600"],
        "motherboard": ["b550"],
        "ram": ["ddr4-16", "ddr4-32"],
        "gpu": ["rx6600", "rtx4060"],
        "ssd": ["nv2-500", "sn580-1"],
        "psu": ["pk550", "pk650"],
        "case": ["matrexx40", "cc560"],
        "cooler": ["ag200", "ag400"],
    }
    for category, ids in subset.items():
        monkeypatch.setitem(GROUPS, category, [ITEMS[i] for i in ids])
    req = RecommendRequest(budget=75000, purpose="gaming")
    candidates = []
    categories = list(subset)
    for combo in product(*(GROUPS[k] for k in categories)):
        build = dict(zip(categories, combo))
        cost = sum(i["estimate_rub"] for i in combo)
        if cost <= req.budget and compatibility(build)["compatible"]:
            score = utility(
                build["cpu"], build["gpu"], build["ram"], build["ssd"], "gaming"
            )
            candidates.append((round(score, 6), -cost))
    result = recommend(req)
    assert (result["score"], -result["total_rub"]) == max(candidates)
