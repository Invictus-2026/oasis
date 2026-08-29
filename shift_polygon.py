import json

dy = -1.5  # shift south by 1.5 degrees

# 1. Update frontend detection.json
with open('frontend/src/mock/detection.json', 'r') as f:
    det = json.load(f)

for slick in det['slicks']:
    poly = slick['polygon']['coordinates'][0]
    for pt in poly:
        pt[1] += dy

for la in det['rejected_lookalikes']:
    poly = la['polygon']['coordinates'][0]
    for pt in poly:
        pt[1] += dy

with open('frontend/src/mock/detection.json', 'w') as f:
    json.dump(det, f, indent=1)

# 2. Update frontend case.json
with open('frontend/src/mock/case.json', 'r') as f:
    case = json.load(f)

case['center'][1] += dy
case['bbox']['south'] += dy
case['bbox']['north'] += dy

with open('frontend/src/mock/case.json', 'w') as f:
    json.dump(case, f, indent=1)

print("Shifted!")
