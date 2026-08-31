from shapely.geometry import Point, LineString, Polygon
from shapely.ops import substring

poly = Polygon([(0,0), (0,10), (10,10), (10,0)])
boundary = LineString(poly.exterior.coords)

d1 = 25
d2 = 5

pathA = substring(boundary, d1, d2)
print("Path A (d1->d2):", list(pathA.coords))

part1 = substring(boundary, d1, boundary.length)
part2 = substring(boundary, 0, d2)
pathB_coords = list(part1.coords) + list(part2.coords)[1:]
print("Path B (wrap forward):", pathB_coords)
