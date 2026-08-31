from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

p1 = Polygon([(0,0), (0,1), (1,1), (1,0)])
p2 = Polygon([(0.5,0.5), (0.5, 1.5), (1.5, 1.5), (1.5, 0.5)])
p3 = Polygon([(10,10), (10,11), (11,11), (11,10)])

combined = unary_union([p1, p2, p3])
print("Combined type:", combined.geom_type)

if combined.geom_type == 'MultiPolygon':
    hulled = MultiPolygon([geom.convex_hull for geom in combined.geoms])
else:
    hulled = combined.convex_hull

print("Hulled type:", hulled.geom_type)
print(hulled)
