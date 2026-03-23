import time
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class MetricsStore:
    _start_time: float = field(default_factory=time.time)
    _total_requests: int = 0
    _successful_requests: int = 0
    _failed_requests: int = 0
    _requests_by_type: Dict[str, int] = field(default_factory=dict)
    _requests_by_env: Dict[str, int] = field(default_factory=dict)
    _durations: list = field(default_factory=list)
    _http_requests_total: int = 0

    def reset(self):
        self._start_time = time.time()
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._requests_by_type = {}
        self._requests_by_env = {}
        self._durations = []
        self._http_requests_total = 0

    def record_operational_request(
        self,
        request_type: str,
        environment: str,
        success: bool,
        duration_ms: float,
    ):
        self._total_requests += 1
        if success:
            self._successful_requests += 1
        else:
            self._failed_requests += 1
        self._requests_by_type[request_type] = self._requests_by_type.get(request_type, 0) + 1
        self._requests_by_env[environment] = self._requests_by_env.get(environment, 0) + 1
        self._durations.append(duration_ms)

    def record_http_request(self, method: str, path: str, status_code: int, duration_ms: float):
        self._http_requests_total += 1

    @property
    def total_requests(self) -> int:
        return self._total_requests

    @property
    def successful_requests(self) -> int:
        return self._successful_requests

    @property
    def failed_requests(self) -> int:
        return self._failed_requests

    @property
    def requests_by_type(self) -> dict:
        return dict(self._requests_by_type)

    @property
    def requests_by_environment(self) -> dict:
        return dict(self._requests_by_env)

    @property
    def average_duration_ms(self) -> float:
        if not self._durations:
            return 0.0
        return round(sum(self._durations) / len(self._durations), 2)

    @property
    def http_requests_total(self) -> int:
        return self._http_requests_total

    @property
    def uptime_seconds(self) -> float:
        return round(time.time() - self._start_time, 2)


metrics_store = MetricsStore()
