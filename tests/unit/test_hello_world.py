import pytest

from hello_world import HelloWorld

object = HelloWorld()


@pytest.mark.unit
def test_get_message():
    assert object.get_message() == "Hello, World!"


@pytest.mark.unit
def test_get_message_type():
    assert type(object.get_message()) == str