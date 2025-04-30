import pytest

from hello_world import HelloWorld

object = HelloWorld()

@pytest.mark.integration
def test_get_message_length():
    assert len(object.get_message()) == 13
