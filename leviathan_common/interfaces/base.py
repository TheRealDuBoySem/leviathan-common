from abc import ABC, abstractmethod
from leviathan_common.models.trade_tick import TradeTick

class IPriceObserver(ABC):
    @abstractmethod
    async def on_price_update(self, tick: TradeTick) -> None:
        """
        Méthode de callback appelée lors de la réception d'un nouveau tick.
        """
        pass # pragma: no cover
