import json, math

with open('src/mock/forecast.json') as f:
    fc = json.load(f)

t0 = fc['particles_timeline'][0]
t8 = fc['particles_timeline'][1]

target_hours = [0, 2, 4, 8, 16, 24, 36, 48, 72]

def eff_h(h):
    if h <= 8: return h
    return 8 + math.sqrt(h - 8) * 3.5

# 1. Extrapolate particles
new_timeline = []
for h in target_hours:
    if h == 0:
        new_timeline.append(t0)
        continue
    
    eh = eff_h(h)
    
    points = []
    for p0, p8 in zip(t0['points'], t8['points']):
        vx = (p8[0] - p0[0]) / 8.0
        vy = (p8[1] - p0[1]) / 8.0
        points.append([p0[0] + vx * eh, p0[1] + vy * eh])
    
    new_timeline.append({
        "t_offset_hours": float(h),
        "points": points
    })

fc['particles_timeline'] = new_timeline

# 2. Extrapolate cones
c0_50 = next(c for c in fc['cone'] if c['t_offset_hours'] == 0 and c['percentile'] == 50)
c0_90 = next(c for c in fc['cone'] if c['t_offset_hours'] == 0 and c['percentile'] == 90)
c8_50 = next(c for c in fc['cone'] if c['t_offset_hours'] == 8 and c['percentile'] == 50)
c8_90 = next(c for c in fc['cone'] if c['t_offset_hours'] == 8 and c['percentile'] == 90)

def center(ring):
    return sum(p[0] for p in ring)/len(ring), sum(p[1] for p in ring)/len(ring)

def extrapolate_cone(c0, c8, h):
    eh = eff_h(h)
    ring0 = c0['polygon']['coordinates'][0]
    ring8 = c8['polygon']['coordinates'][0]
    
    cx0, cy0 = center(ring0)
    cx8, cy8 = center(ring8)
    
    vx = (cx8 - cx0) / 8.0
    vy = (cy8 - cy0) / 8.0
    
    ring_new = []
    for p0, p8 in zip(ring0, ring8):
        dx0, dy0 = p0[0]-cx0, p0[1]-cy0
        dx8, dy8 = p8[0]-cx8, p8[1]-cy8
        
        g_dx = (dx8 - dx0) / 8.0
        g_dy = (dy8 - dy0) / 8.0
        
        cxh = cx0 + vx * eh
        cyh = cy0 + vy * eh
        
        dxh = dx0 + g_dx * eh
        dyh = dy0 + g_dy * eh
        
        ring_new.append([cxh + dxh, cyh + dyh])
        
    return {
        "t_offset_hours": float(h),
        "percentile": c0['percentile'],
        "polygon": {"type": "Polygon", "coordinates": [ring_new]}
    }

new_cones = []
for h in target_hours:
    if h == 0:
        new_cones.append(c0_50)
        new_cones.append(c0_90)
    elif h == 8:
        new_cones.append(c8_50)
        new_cones.append(c8_90)
    else:
        new_cones.append(extrapolate_cone(c0_50, c8_50, h))
        new_cones.append(extrapolate_cone(c0_90, c8_90, h))

fc['cone'] = new_cones

# 3. Extrapolate path
path = fc['centroid_path']['coordinates']
p0 = path[0]
p8 = path[1] if len(path) > 1 else path[0]
vx = (p8[0] - p0[0]) / 8.0
vy = (p8[1] - p0[1]) / 8.0

new_path = []
for h in target_hours:
    eh = eff_h(h)
    new_path.append([p0[0] + vx * eh, p0[1] + vy * eh])

fc['centroid_path']['coordinates'] = new_path

with open('src/mock/forecast.json', 'w') as f:
    json.dump(fc, f, separators=(',', ':'))

print('Extrapolated forecast.json with dampening')
