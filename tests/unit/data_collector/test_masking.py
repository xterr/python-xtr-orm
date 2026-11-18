from __future__ import annotations

import pytest

from xtr_orm.data_collector._masking import MASK, is_sensitive, masked


@pytest.mark.parametrize(
    "name",
    ["password", "user_password", "Secret", "access_token", "passwd", "api_key", "APIKEY"],
)
def test_a_credential_named_parameter_is_sensitive(name: str) -> None:
    assert is_sensitive(name)


@pytest.mark.parametrize("name", ["authorization", "Proxy-Authorization", "cookie", "x-api-key"])
def test_a_credential_carrying_header_name_is_sensitive(name: str) -> None:
    assert is_sensitive(name)


def test_an_ordinary_name_is_not_sensitive() -> None:
    assert not is_sensitive("email")


def test_a_mapping_has_its_credential_values_masked() -> None:
    assert masked({"email": "a@b.c", "password": "hunter2"}) == {"email": "a@b.c", "password": MASK}


def test_every_mapping_of_a_list_is_masked_and_the_list_kept() -> None:
    assert masked([{"token": "t"}, {"token": "u"}]) == [{"token": MASK}, {"token": MASK}]


def test_a_tuple_of_mappings_stays_a_tuple() -> None:
    assert masked(({"secret": "s"},)) == ({"secret": MASK},)


def test_positional_parameters_are_kept_as_they_are() -> None:
    assert masked(("hunter2", 1)) == ("hunter2", 1)


def test_a_key_that_is_not_text_is_kept() -> None:
    assert masked({1: "one"}) == {1: "one"}


def test_no_parameters_are_kept_as_none() -> None:
    assert masked(None) is None
