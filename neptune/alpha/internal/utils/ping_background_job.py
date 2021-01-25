#
# Copyright (c) 2020, Neptune Labs Sp. z o.o.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import logging
from datetime import datetime

from typing import TYPE_CHECKING, Optional

from neptune.alpha.attributes.constants import SYSTEM_PING_TIME_ATTRIBUTE_PATH
from neptune.alpha.internal.background_job import BackgroundJob
from neptune.alpha.internal.threading.daemon import Daemon

if TYPE_CHECKING:
    from neptune.alpha.experiment import Experiment

_logger = logging.getLogger(__name__)


class PingBackgroundJob(BackgroundJob):

    def __init__(self, period: float = 10):
        self._period = period
        self._thread = None
        self._started = False

    def start(self, experiment: 'Experiment'):
        self._thread = self.ReportingThread(self._period, experiment)
        self._thread.start()
        self._started = True

    def stop(self):
        if not self._started:
            return
        self._thread.interrupt()

    def join(self, seconds: Optional[float] = None):
        if not self._started:
            return
        self._thread.join(seconds)

    class ReportingThread(Daemon):

        def __init__(
                self,
                period: float,
                experiment: 'Experiment'):
            super().__init__(sleep_time=period)
            self._experiment = experiment

        def work(self) -> None:
            self._experiment[SYSTEM_PING_TIME_ATTRIBUTE_PATH] = datetime.now()
