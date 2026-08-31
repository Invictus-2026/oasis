import requests
import json

url = "http://localhost:8000/api/drift/hindcast"
payload = {
    "slick_id": "adhoc-123",
    "hours": 24,
    "n_particles": 100,
    "custom_polygon": {
        "type": "Polygon",
        "coordinates": [[[-90.14, 28.39], [-90.06, 28.40], [-89.99, 28.43], [-89.99, 28.45], [-90.10, 28.44], [-90.14, 28.39]]]
    },
    "mock_wind_dir_deg": 180
}

response = requests.post(url, json=payload)
print(response.status_code)
if response.status_code != 200:
    print(response.text)
else:
    print("Success, returned particles:", len(response.json()["particles_timeline"]))
