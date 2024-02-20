"""
Copyright 2024 b<>com

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from typing import Any, Callable, Optional, TYPE_CHECKING

from simpy.core import BoundClass
from simpy.resources.store import FilterStore, StoreGet, StorePut


class PriorityFilterStoreGet(StoreGet):
    """Request to get an *item* from the *store* matching the *filter*. The
    request is triggered once there is such an item available in the store.

    *filter* is a function receiving one item. It should return ``True`` for
    items matching the filter criterion. The default function returns ``True``
    for all items, which makes the request to behave exactly like
    :class:`StoreGet`.

    """

    def __init__(
        self,
        resource: "PriorityFilterStore",
        filter: Callable[[Any], bool] = lambda item: True,
    ):
        self.filter = filter
        """The filter function to filter items in the store."""
        super().__init__(resource)


class PriorityFilterStore(FilterStore):
    """Resource with *capacity* slots for storing arbitrary objects supporting
    filtered get requests **and** in priority order.

    Get requests can be customized with a filter function to only trigger for
    items for which said filter function returns ``True``.
    If multiple items trigger the filter, select the lowest item using priority.

    :class:`PriorityFilterStore` maintains items in sorted order such that
    the smallest items value are retreived first from the store.

    All items in a *PriorityFilterStore* instance must be orderable; which is to
    say that items must implement :meth:`~object.__lt__()`. To use unorderable
    items with *PriorityFilterStore*, use :class:`PriorityItem`.
    """

    if TYPE_CHECKING:

        def get(
            self, filter: Callable[[Any], bool] = lambda item: True
        ) -> PriorityFilterStoreGet:
            """Request to get an *item*, for which *filter* returns ``True``,
            out of the store."""
            return PriorityFilterStoreGet(self, filter)

    else:
        get = BoundClass(PriorityFilterStoreGet)

    def _do_put(self, event: StorePut) -> Optional[bool]:
        if len(self.items) < self._capacity:
            # heappush(self.items, event.item)
            self.items.append(event.item)
            event.succeed()
        return None

    def _do_get(  # type: ignore[override] # noqa: F821
        self, event: PriorityFilterStoreGet
    ) -> Optional[bool]:
        suitable = []
        # Filter Get
        for item in self.items:
            if event.filter(item):
                suitable.append(item)
        # If multiple items trigger the filter, select with priority
        if suitable:
            winner = min(suitable)
            self.items.remove(winner)
            event.succeed(winner)
            return True
        """
        # If no item triggers the filter, fall back to selecting using item priority.
        else:
            # Else, select any item according to priority
            if self.items:
                event.succeed(heappop(self.items))
            return True
        """
