"""Commission arithmetic — the money split must never lose a Star."""

from __future__ import annotations

import pytest

from app.services.pricing import split_amount


@pytest.mark.parametrize(
    ("amount", "percent", "commission", "seller"),
    [
        (500, 10, 50, 450),
        (100, 10, 10, 90),
        (9, 10, 0, 9),  # sub-1% amounts round the commission down
        (101, 10, 10, 91),  # remainder goes to the seller
        (1000, 0, 0, 1000),
        (1000, 50, 500, 500),
        (333, 15, 49, 284),
    ],
)
def test_split_amount(amount, percent, commission, seller):
    split = split_amount(amount, percent)
    assert split.commission_stars == commission
    assert split.seller_stars == seller
    assert split.commission_stars + split.seller_stars == amount


def test_split_rejects_invalid_input():
    with pytest.raises(ValueError):
        split_amount(0, 10)
    with pytest.raises(ValueError):
        split_amount(100, 51)
    with pytest.raises(ValueError):
        split_amount(100, -1)
