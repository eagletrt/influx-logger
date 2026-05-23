import json
from statistics import geometric_mean, mean

class QueryPerformance:
    def __init__(self, influx_time: int, mongo_time: int, time_unit: str = "ms"):
        self.influx_time: int = influx_time
        self.mongo_time: int = mongo_time
        self.influx_advantage: int = mongo_time - influx_time
        self.time_unit: str = time_unit
    
    def __str__(self) -> str:
        return f"InfluxDB: {self.influx_time} {self.time_unit}, MongoDB: {self.mongo_time} {self.time_unit}, Advantage: {self.influx_advantage} {self.time_unit}"

    def to_json(self) -> json:
        return {
            "influx_time": self.influx_time,
            "mongo_time": self.mongo_time,
            "influx_advantage": self.influx_advantage
        }

class PerformanceQueries:
    def __init__(self, query: QueryPerformance | None = None):
        self.queries: list[QueryPerformance] = []
        if query is not None:
            self.queries.append(query)
        self.influx_mean_time: float = 0.0
        self.mongo_mean_time: float = 0.0
        self.influx_advantage: float = 0.0
        self.update_advantage()

    def update_advantage(self) -> None:
        if self.queries:
            self.influx_advantage = mean(q.influx_advantage for q in self.queries)
        
    def update_means(self) -> None:
        if self.queries:
            self.influx_mean_time = float(geometric_mean(q.influx_time for q in self.queries if q.influx_time != 0))
            self.mongo_mean_time = float(geometric_mean(q.mongo_time for q in self.queries if q.mongo_time != 0))
            self.update_advantage()

    def add(self, query: QueryPerformance) -> None:
        self.queries.append(query)
        self.update_means()

    def __str__(self) -> str:
        return str(json.dumps(self.to_json(), indent=2))
    
    def to_json(self) -> json:
        j:json = {
            "queries": [q.to_json() for q in self.queries],
            "influx_mean_time": f"{self.influx_mean_time:.3f}",
            "mongo_mean_time": f"{self.mongo_mean_time:.3f}",
            "influx_advantage": f"{self.influx_advantage:.3f}"
        }
        return j

class Performances:
    def __init__(self, time_unit: str = "ms"):
        self.performances: dict[str, PerformanceQueries] = {}
        self.influx_advantage: float = 0.0
        self.influx_mean_time: float = 0.0
        self.mongo_mean_time: float = 0.0
        self.time_unit: str = time_unit

    def add(self, name: str, query: QueryPerformance) -> None:
        if name not in self.performances:
            self.performances[name] = PerformanceQueries()
        self.performances[name].add(query)
        self.performances[name].update_advantage()
        self.performances[name].update_means()
        self.update_overall_advantage()
    
    def update_overall_advantage(self) -> None:
        if self.performances:
            # compute the arithmetic mean of all individual query influx_advantage values
            total = sum(performance.influx_advantage for performance in self.performances.values())
            self.influx_advantage = float(total) / len(self.performances)
            self.influx_mean_time = float(geometric_mean(performance.influx_mean_time for performance in self.performances.values() if performance.influx_mean_time != 0))
            self.mongo_mean_time = float(geometric_mean(performance.mongo_mean_time for performance in self.performances.values() if performance.mongo_mean_time != 0))

    def update_advantage(self) -> None:
        if self.queries:
            # compute the arithmetic mean of all individual query influx_advantage values
            total = sum(q.influx_advantage for q in self.queries)
            self.influx_advantage = float(total) / len(self.queries)
        
    def update_means(self) -> None:
        if self.queries:
            self.influx_mean_time = float(geometric_mean(q.influx_time for q in self.queries if q.influx_time != 0))
            self.mongo_mean_time = float(geometric_mean(q.mongo_time for q in self.queries if q.mongo_time != 0))
            self.update_advantage()

    def __str__(self) -> str:
        return str(json.dumps(self.to_json(), indent=2))
    
    def to_json(self) -> json:
        j:json = {
            "overall_influx_advantage": f"{self.influx_advantage:.3f}",
            "overall_influx_mean_time": f"{self.influx_mean_time:.3f}",
            "overall_mongo_mean_time": f"{self.mongo_mean_time:.3f}",
            "time_unit": self.time_unit
        }
        return j
