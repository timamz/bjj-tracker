from bjj_bot.services.rank import RankError, RankState, add_stripe, promote_belt


def test_add_stripe_increments() -> None:
    state = add_stripe(RankState(belt="white", stripes=2))
    assert state.stripes == 3
    assert state.belt == "white"


def test_add_stripe_rejects_fifth() -> None:
    try:
        add_stripe(RankState(belt="blue", stripes=4))
    except RankError:
        return
    raise AssertionError("Expected RankError")


def test_promote_belt_resets_stripes() -> None:
    state = promote_belt(RankState(belt="white", stripes=4))
    assert state.belt == "blue"
    assert state.stripes == 0

