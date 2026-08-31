from shapely.geometry import Point, LineString, Polygon, MultiPoint
from shapely.ops import split
import time

poly = Polygon([(0,0), (0,10), (10,10), (10,0)])
boundary = poly.exterior

pt1 = Point(0, 5)
pt2 = Point(10, 5)

# Split boundary by the two points
result = split(boundary, MultiPoint([pt1, pt2]))
print(result.geom_type)
for geom in result.geoms:
    print(geom.geom_type, list(geom.coords))
