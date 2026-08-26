import type { HindcastResponse, ForecastResponse, AttributeResponse } from "../api/types";

function rotateAndShift(
  p: [number, number], 
  origin: [number, number], 
  dx: number, 
  dy: number, 
  thetaRad: number,
  aspect: number
): [number, number] {
  if (thetaRad === 0) {
    return [p[0] + dx, p[1] + dy];
  }
  
  const relLon = p[0] - origin[0];
  const relLat = p[1] - origin[1];
  
  const x = relLon * aspect;
  const y = relLat;
  
  const rx = x * Math.cos(thetaRad) - y * Math.sin(thetaRad);
  const ry = x * Math.sin(thetaRad) + y * Math.cos(thetaRad);
  
  return [
    rx / aspect + origin[0] + dx,
    ry + origin[1] + dy
  ];
}

export function shiftHindcast(mock: unknown, dx: number, dy: number, mockOrigin: [number, number], thetaDeg = 0): HindcastResponse {
  const m = JSON.parse(JSON.stringify(mock)) as HindcastResponse;
  const thetaRad = (thetaDeg * Math.PI) / 180;
  const aspect = Math.cos((mockOrigin[1] * Math.PI) / 180);
  
  m.particles_timeline.forEach(frame => {
    frame.points = frame.points.map(p => rotateAndShift(p, mockOrigin, dx, dy, thetaRad, aspect));
  });
  
  m.cone.forEach(c => {
    if (c.polygon.type === "Polygon") {
      c.polygon.coordinates = c.polygon.coordinates.map(ring =>
        ring.map(p => rotateAndShift(p, mockOrigin, dx, dy, thetaRad, aspect))
      );
    }
  });
  
  m.origin_estimate.point = rotateAndShift(m.origin_estimate.point, mockOrigin, dx, dy, thetaRad, aspect);
  
  return m;
}

export function shiftForecast(mock: unknown, dx: number, dy: number, mockOrigin: [number, number], thetaDeg = 0): ForecastResponse {
  const m = JSON.parse(JSON.stringify(mock)) as ForecastResponse;
  const thetaRad = (thetaDeg * Math.PI) / 180;
  const aspect = Math.cos((mockOrigin[1] * Math.PI) / 180);
  
  m.particles_timeline.forEach(frame => {
    frame.points = frame.points.map(p => rotateAndShift(p, mockOrigin, dx, dy, thetaRad, aspect));
  });
  
  m.cone.forEach(c => {
    if (c.polygon.type === "Polygon") {
      c.polygon.coordinates = c.polygon.coordinates.map(ring =>
        ring.map(p => rotateAndShift(p, mockOrigin, dx, dy, thetaRad, aspect))
      );
    }
  });
  
  if (m.centroid_path.type === "LineString") {
    m.centroid_path.coordinates = m.centroid_path.coordinates.map(p => rotateAndShift(p, mockOrigin, dx, dy, thetaRad, aspect));
  }
  
  return m;
}

export function shiftAttribution(mock: unknown, dx: number, dy: number, mockOrigin: [number, number], thetaDeg = 0): AttributeResponse {
  const m = JSON.parse(JSON.stringify(mock)) as AttributeResponse;
  const thetaRad = (thetaDeg * Math.PI) / 180;
  const aspect = Math.cos((mockOrigin[1] * Math.PI) / 180);
  
  m.candidates.forEach(c => {
    if (c.track.type === "LineString") {
      c.track.coordinates = c.track.coordinates.map(p => rotateAndShift(p, mockOrigin, dx, dy, thetaRad, aspect));
    }
    c.gaps.forEach(g => {
      if (g.interpolated_path?.type === "LineString") {
        g.interpolated_path.coordinates = g.interpolated_path.coordinates.map(p => rotateAndShift(p, mockOrigin, dx, dy, thetaRad, aspect));
      }
    });
  });
  
  if (m.all_tracks) {
    m.all_tracks.features.forEach(f => {
      if (f.geometry.type === "LineString") {
        f.geometry.coordinates = f.geometry.coordinates.map(p => rotateAndShift(p, mockOrigin, dx, dy, thetaRad, aspect));
      }
    });
  }
  
  return m;
}
