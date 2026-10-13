from verify_town_shop_consumption import derive


def test_default_shop_semantics_and_egg_bound():
    result = derive()
    defaults = result["defaults"]
    egg = result["egg"]

    assert defaults == {
        "turns_per_day": 24,
        "shop_unlock_interval_days": 3,
        "shop_sell_interval_turns": 4,
        "town_center_sell_interval_turns": 24,
        "shop_ticks_per_day": 6,
        "town_center_ticks_per_day": 1,
        "max_shop_instances": 8,
    }
    assert egg["consumer_shops"] == ["BAKERY", "BRUNCH_SPOT"]
    assert egg["multiplier_per_tick"] == 1
    assert egg["per_shop_per_day"] == 6
    assert egg["max_instances_through_day8"] == 2
    assert egg["day8_total_demand_upper_bound_including_center"] == 13
    assert egg["full_cap_total_demand_upper_bound_including_center"] == 49


def test_only_single_product_shops_receive_double_multiplier():
    result = derive()
    assert result["doubled_single_product_shops"] == ["PET_CAFE", "YARN_STORE"]
    assert result["max_daily_demand_at_eight_shop_cap_including_center"] == {
        "WHEAT": 49,
        "CARROT": 97,
        "TOMATO": 49,
        "STRAWBERRY": 49,
        "MELON": 1,
        "EGG": 49,
        "MILK": 49,
        "WOOL": 97,
        "FERTILIZER": 0,
    }
