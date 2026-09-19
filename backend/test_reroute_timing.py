import unittest
from shapely.geometry import LineString, shape
from app.api.reroute import reroute_vessel
from app.core.schemas import RerouteRequest
OIL = {"type":"Polygon","coordinates":[[[1,-.1],[1.2,-.1],[1.2,.1],[1,.1],[1,-.1]]]}
class RoutingTimingTests(unittest.TestCase):
    def route(self, **kw):
        args=dict(start_point=[0,0],end_point=[2,0],obstacles=[OIL]); args.update(kw)
        return reroute_vessel(RerouteRequest(**args))
    def test_unknown_detours(self):
        r=self.route(re_route_needed=False)
        self.assertTrue(r.is_rerouted)
        self.assertTrue(LineString(r.rerouted_path).relate_pattern(shape(r.exclusion_zone).buffer(-1e-9),'F********'))
        self.assertEqual(tuple(r.rerouted_path[0]),(0,0))
        self.assertEqual(tuple(r.rerouted_path[-1]),(2,0))
    def test_early_clearance(self):
        self.assertEqual(self.route(clearance_hours=1,clearance_buffer_hours=1).decision,'direct_after_clearance')
    def test_late_clearance(self):
        self.assertTrue(self.route(clearance_hours=5).is_rerouted)
    def test_speed(self):
        self.assertFalse(self.route(clearance_hours=2,clearance_buffer_hours=1,vessel_speed_knots=10).is_rerouted)
        self.assertTrue(self.route(clearance_hours=2,clearance_buffer_hours=1,vessel_speed_knots=30).is_rerouted)
    def test_equality(self):
        eta=self.route().hazard_arrival_hours
        self.assertTrue(self.route(clearance_hours=eta,clearance_buffer_hours=0).is_rerouted)
    def test_no_crossing(self):
        self.assertEqual(self.route(start_point=[0,1],end_point=[2,1]).decision,'direct_clear')
    def test_unavailable(self):
        for kw in [dict(obstacles=[]),dict(obstacles=[{}])]:
            self.assertEqual(self.route(**kw).decision,'unavailable')
    def test_waypoint_inside_hazard_is_escaped_not_blocked(self):
        # A waypoint dropped inside the hazard boundary used to be a hard
        # dead end ('unavailable'). It should instead be nudged to the
        # nearest clear point and still produce a real avoiding route that
        # departs from the vessel's actual clicked position.
        r=self.route(start_point=[1.1,0])
        self.assertEqual(r.decision,'reroute')
        self.assertTrue(r.is_rerouted)
        self.assertEqual(tuple(r.rerouted_path[0]),(1.1,0))
        self.assertEqual(tuple(r.rerouted_path[-1]),(2,0))
    def test_destination_eta_not_used(self):
        self.assertTrue(self.route(start_point=[.9,0],end_point=[20,0],clearance_hours=1).is_rerouted)
if __name__=='__main__': unittest.main()
