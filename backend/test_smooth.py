def smooth_path(coords, iterations=2):
    if len(coords) < 3:
        return coords
    for _ in range(iterations):
        smoothed = [coords[0]]
        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i+1]
            q = (0.75 * p1[0] + 0.25 * p2[0], 0.75 * p1[1] + 0.25 * p2[1])
            r = (0.25 * p1[0] + 0.75 * p2[0], 0.25 * p1[1] + 0.75 * p2[1])
            smoothed.append(q)
            smoothed.append(r)
        smoothed.append(coords[-1])
        coords = smoothed
    return coords

pts = [(0,0), (1,1), (2,0)]
print(smooth_path(pts, 1))
