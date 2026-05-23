import json
from statistics import geometric_mean, mean
import matplotlib.pyplot as plt
import math

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
    def __init__(self, query_name: str, query: QueryPerformance | None = None):
        self.query_name: str = query_name
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
            "query_name": self.query_name,
            "queries": [q.to_json() for q in self.queries],
            "influx_mean_time": f"{self.influx_mean_time:.3f}",
            "mongo_mean_time": f"{self.mongo_mean_time:.3f}",
            "influx_advantage": f"{self.influx_advantage:.3f}"
        }
        return j
    
    def plot(self, file_to_save: str = "", title: str = "") -> None:
        if title == "":
            title = self.query_name
        if file_to_save == "":
            file_to_save = f"{self.query_name}.png"
        if not self.queries:
            print(f"No queries to plot for {title}")
            return
        influx_times = [q.influx_time for q in self.queries]
        mongo_times = [q.mongo_time for q in self.queries]
        x = range(1, len(self.queries) + 1)
        plt.figure(figsize=(10, 5))
        plt.plot(x, influx_times, label="InfluxDB")
        plt.plot(x, mongo_times, label="MongoDB")
        plt.title(title)
        plt.xlabel("Query Run")
        plt.ylabel(f"Time ({self.queries[0].time_unit})")
        plt.legend()
        plt.grid()
        if file_to_save:
            plt.savefig(file_to_save)
        plt.show()

class Performances:
    def __init__(self, time_unit: str = "ms"):
        self.performances: dict[str, PerformanceQueries] = {}
        self.influx_advantage: float = 0.0
        self.influx_mean_time: float = 0.0
        self.mongo_mean_time: float = 0.0
        self.time_unit: str = time_unit

    def add(self, name: str, query: QueryPerformance) -> None:
        if name not in self.performances:
            self.performances[name] = PerformanceQueries(query_name=name, query=query)
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
    
    def plot_all(self, save: bool = False) -> None:
        if not self.performances:
            print("No performances to plot")
            return
        n = len(self.performances)
        cols = 4
        rows = math.ceil(n / cols) if n > 0 else 1
        fig, axes = plt.subplots(rows, cols, figsize=(10 * cols, 5 * rows), squeeze=False)
        for ax, (name, performance) in zip(axes.flatten(), self.performances.items()):
            if not performance.queries:
                ax.set_title(f"{name} (no queries)")
                ax.axis("off")
                continue
            influx_times = [q.influx_time for q in performance.queries]
            mongo_times = [q.mongo_time for q in performance.queries]
            x = range(1, len(performance.queries) + 1)
            ax.plot(x, influx_times, label="InfluxDB", marker='o')
            ax.plot(x, mongo_times, label="MongoDB", marker='o')
            ax.set_title(name)
            ax.set_xlabel("Query Run")
            ax.set_ylabel(f"Time ({performance.queries[0].time_unit})")
            ax.legend()
            ax.grid()
            if save:
                fig.savefig(f"{name}.png")
        plt.tight_layout()
        plt.show()
    
    @staticmethod
    def short_keys(keys, length: int = 25) -> list[str]:
        return [s if len(s) <= length else s[:length-3] + "..." for s in keys]

    def plot_overall(self, file_to_save: str = "") -> None:
        if not self.performances:
            print("No performances to plot")
            return
        if file_to_save == "":
            file_to_save = "overall_performance.png"
        influx_means = [performance.influx_mean_time for performance in self.performances.values()]
        mongo_means = [performance.mongo_mean_time for performance in self.performances.values()]
        plt.figure(figsize=(10, 5))
        x = range(len(influx_means))
        width = 0.35
        plt.bar([i - width/2 for i in x], influx_means, width, label="InfluxDB Mean Time", alpha=0.7, edgecolor="black")
        plt.bar([i + width/2 for i in x], mongo_means, width, label="MongoDB Mean Time", alpha=0.7, edgecolor="black")
        plt.title("Overall Performance Comparison")
        plt.xlabel("Query")
        plt.ylabel(f"Mean Time ({self.time_unit})")
        plt.xticks(x, Performances.short_keys(list(self.performances.keys())), rotation=45, ha='right')
        plt.legend()
        plt.grid(axis='y')
        plt.tight_layout()
        if file_to_save:
            plt.savefig(file_to_save)
        plt.show()
    
    def save_all(self, file:str = "performances.json") -> None:
        with open(file, "w") as f:
            json.dump({name: performance.to_json() for name, performance in self.performances.items()}, f, indent=2)
    
    @staticmethod
    def load_from_file(file:str = "performances.json") -> 'Performances':
        with open(file, "r") as f:
            data = json.load(f)
            performances = Performances()
            for name, performance_data in data.items():
                performance_queries = PerformanceQueries(query_name=name)
                for query_data in performance_data["queries"]:
                    query_performance = QueryPerformance(
                        influx_time=query_data["influx_time"],
                        mongo_time=query_data["mongo_time"]
                    )
                    performance_queries.add(query_performance)
                performance_queries.influx_mean_time = float(performance_data["influx_mean_time"])
                performance_queries.mongo_mean_time = float(performance_data["mongo_mean_time"])
                performance_queries.influx_advantage = float(performance_data["influx_advantage"])
                performances.performances[name] = performance_queries
            performances.update_overall_advantage()
            return performances
