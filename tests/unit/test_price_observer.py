import pytest
from leviathan_common.interfaces.base import IPriceObserver
from leviathan_common.models.trade_tick import TradeTick

def test_price_observer_interface():
    # Verify that IPriceObserver cannot be instantiated directly (abstract class)
    with pytest.raises(TypeError):
        IPriceObserver()

    # Define a concrete subclass to test instantiation and method signature
    class DummyPriceObserver(IPriceObserver):
        def __init__(self):
            self.tick_received = None

        async def on_price_update(self, tick: TradeTick) -> None:
            self.tick_received = tick

    observer = DummyPriceObserver()
    assert observer is not None
