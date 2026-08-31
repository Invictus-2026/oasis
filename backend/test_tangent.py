from shapely.geometry import Point, Polygon, MultiPoint, LineString
from shapely.ops import unary_union

poly = Polygon([(0, -10), (0, 10), (10, 10), (10, -10)])
pt1 = Point(-5, 0)
pt2 = Point(15, 0)

# The intersection approach:
orig_line = LineString([pt1, pt2])
intersection = poly.exterior.intersection(orig_line)
pts = sorted(list(intersection.geoms), key=lambda p: pt1.distance(p))
d1 = poly.exterior.project(pts[0])
d2 = poly.exterior.project(pts[-1])
# Path A: [-5, 0] -> [0, 0] -> [0, -10] -> [10, -10] -> [10, 0] -> [15, 0]
# Distance A = 5 + 10 + 10 + 10 + 5 = 40

# The convex hull approach:
hull = unary_union([poly, pt1, pt2]).convex_hull
# Hull boundary is a ring containing pt1 and pt2!
hull_line = LineString(hull.exterior.coords)
d_pt1 = hull_line.project(pt1)
d_pt2 = hull_line.project(pt2)

from shapely.ops import substring
if d_pt1 > d_pt2:
    d_pt1, d_pt2 = d_pt2, d_pt1
path1 = substring(hull_line, d_pt1, d_pt2)
path2_1 = substring(hull_line, d_pt1, 0)
path2_2 = substring(hull_line, hull_line.length, d_pt2)
path2 = LineString(list(path2_1.coords) + list(path2_2.coords)[1:])

print("Hull Path 1 length:", path1.length)
print("Hull Path 2 length:", path2.length)
# Path 1/2 should be the two tangent paths around the polygon!
