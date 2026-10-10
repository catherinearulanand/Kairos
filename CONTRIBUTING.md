# Contributing to Kairos

## Add a SerpApi engine as a sensor

Each SerpApi engine in Kairos is wrapped as a `Sensor` plugin behind a single interface. To add a new data source, you create a new class extending `Sensor`, implement a `collect` step (or use the default), and write a `parse` function to extract metrics.

### Example: The Demand Sensor (`google_trends`)

Here is how the Demand sensor is implemented:

```python
from kairos.sensors.base import Sensor, ObsDraft, register

@register
class DemandSensor(Sensor):
    id, engines, parser_version = "demand", ["google_trends"], "3"
    
    applies_to = staticmethod(lambda e: bool(e.trends_queries))

    def build_params(self, e):
        # We define the SerpApi query parameters based on the entity
        return [{
            "engine": "google_trends", 
            "q": ",".join(e.trends_queries[:5]),
            "data_type": "TIMESERIES", 
            "geo": "IN",
            "date": "today 12-m", 
            "tz": "-330"
        }]

    def parse(self, e, captures):
        # We take the raw SerpApi JSON and turn it into standard observations
        cap, out = captures[0], []
        
        fetched_day = cap.source_fetched_at.astimezone(IST).date()
        
        for week in cap.json["interest_over_time"]["timeline_data"]:
            start = datetime.fromtimestamp(int(week["timestamp"]), tz=UTC)
            end = start + timedelta(days=7) - timedelta(seconds=1)
            
            for v in week["values"]:
                out.append(ObsDraft(
                    capture=cap, 
                    entity_id=e.entity_id, 
                    sensor=self.id,
                    metric="interest", 
                    dims={"query": v["query"]},
                    value=v.get("extracted_value"), 
                    unit="index_0_100",
                    observed_at=start, 
                    window_start=start, 
                    window_end=end,
                    sample_n=None, 
                    retrieval_complete=True,
                    period_complete=end.astimezone(IST).date() < fetched_day,
                ))
        return out
```

### Steps:
1. Define your `Sensor` subclass and register it.
2. Set `id`, `engines` used, and `parser_version`.
3. Override `build_params(self, e)` to specify how to build SerpApi parameters for a given entity `e`.
4. Override `parse(self, e, captures)` to extract numbers from the raw JSON and yield `ObsDraft` objects.
5. Write a fixture test in `tests/sensors/` that passes offline mock data to your parser.
