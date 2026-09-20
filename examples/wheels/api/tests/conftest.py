# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""This vertical is shopping-only (no merchant agent), so its tests exercise
``MockWheels`` directly rather than joining the cross-vertical contract suite in
``demo_common.tests.fixtures``, which assumes both roles are present."""

import pytest

from shopping_agent import ShoppingSessionContext
from wheels.api.mock_wheels import MockWheels


@pytest.fixture
def backend() -> MockWheels:
    return MockWheels()


@pytest.fixture
def session() -> ShoppingSessionContext:
    return ShoppingSessionContext(session_id="s-1", user_id="demo-user")
