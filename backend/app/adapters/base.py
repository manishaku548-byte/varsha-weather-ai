"""Provider adapter interface for historical-replay (and future live) data.

The rest of the system only ever talks to this interface, so swapping the
controlled synthetic dataset for a real authorised feed later requires a new
adapter implementation only — no service or API rewrite.

Decision-Support Prototype — Not an Official Weather Warning.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class HistoricalReplayAdapter(ABC):
    """Interface every replay/live data provider must implement."""

    #: adapter identifier used in logs and /data/summary
    name: str = "abstract"
    #: data mode reported to the UI: 'synthetic' or 'historical_replay'
    data_mode: str = "replay"

    @abstractmethod
    def load_districts(self) -> pd.DataFrame:
        """District metadata with columns: district_id, district_name, state, latitude, longitude."""

    @abstractmethod
    def load_forecasts(self) -> pd.DataFrame:
        """Forecast records for every source (NWP, ensemble, AI local) in long format."""

    @abstractmethod
    def load_observations(self) -> pd.DataFrame:
        """Observed rainfall/temperature records used for verification and bias history."""

    @abstractmethod
    def describe(self) -> dict[str, str]:
        """Metadata describing provenance, labels and caveats of this provider."""

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<{type(self).__name__} name={self.name!r} data_mode={self.data_mode!r}>"
