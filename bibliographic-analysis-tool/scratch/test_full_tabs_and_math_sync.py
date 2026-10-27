import unittest
import sys, os
sys.path.insert(0, os.path.abspath(os.getcwd()))
import pandas as pd
from features.prisma_assistant import (
    compute_balanced_database_survival,
    _build_horizontal_slr_diagram,
    _build_vertical_slr_diagram,
    DEFAULT_INCLUSION_CRITERIA,
    DEFAULT_EXCLUSION_CRITERIA
)

class TestTabsAndDiagramMathSync(unittest.TestCase):

    def setUp(self):
        # Simulated database setup with multiple databases
        self.db_progressions = {
            'Scopus': {
                'initial': 1200,
                'ics': [
                    ('IC 1', 950, 'Peer-Reviewed Only'),
                    ('IC 2', 400, 'Empirical Studies Only'),
                    ('IC 3', 85, 'Relevant Context')
                ],
                'final': 35
            },
            'IEEE Xplore': {
                'initial': 800,
                'ics': [
                    ('IC 1', 710, 'Peer-Reviewed Only'),
                    ('IC 2', 320, 'Empirical Studies Only'),
                    ('IC 3', 65, 'Relevant Context')
                ],
                'final': 27
            },
            'ACM DL': {
                'initial': 450,
                'ics': [
                    ('IC 1', 390, 'Peer-Reviewed Only'),
                    ('IC 2', 180, 'Empirical Studies Only'),
                    ('IC 3', 50, 'Relevant Context')
                ],
                'final': 21
            }
        }
        
        self.ec_data = [
            {'id': 'EC 1', 'title': 'Out of Domain Scope', 'count': 60, 'remaining': 140},
            {'id': 'EC 2', 'title': 'No Concrete Evaluation', 'count': 40, 'remaining': 100},
            {'id': 'EC 3', 'title': 'Short Paper / Poster', 'count': 17, 'remaining': 83}
        ]
        
        self.user_ics = [
            {'id': 'IC 1', 'title': 'Peer-Reviewed Only'},
            {'id': 'IC 2', 'title': 'Empirical Studies Only'},
            {'id': 'IC 3', 'title': 'Relevant Context'}
        ]

    def test_mathematical_invariants(self):
        """Verify the mathematical equations across the entire pipeline."""
        total_raw_hits = sum(d['initial'] for d in self.db_progressions.values())
        self.assertEqual(total_raw_hits, 1200 + 800 + 450) # 2450

        total_screen_in = sum(d['ics'][-1][1] for d in self.db_progressions.values())
        self.assertEqual(total_screen_in, 85 + 65 + 50) # 200

        total_excluded = sum(ec['count'] for ec in self.ec_data)
        self.assertEqual(total_excluded, 60 + 40 + 17) # 117

        expected_final = total_screen_in - total_excluded
        self.assertEqual(expected_final, 83)
        self.assertEqual(self.ec_data[-1]['remaining'], expected_final)

        # Test compute_balanced_database_survival
        finals = compute_balanced_database_survival(
            self.db_progressions,
            total_screen_in,
            total_excluded
        )
        self.assertEqual(sum(finals.values()), expected_final)
        
        # Verify each DB final <= intake
        for db, fin in finals.items():
            intake = self.db_progressions[db]['ics'][-1][1]
            self.assertLessEqual(fin, intake)
            self.assertGreaterEqual(fin, 0)

    def test_horizontal_flowchart_dot_contains_exact_numbers(self):
        """Verify that horizontal DOT output reflects the exact numbers."""
        total_screen_in = sum(d['ics'][-1][1] for d in self.db_progressions.values())
        total_excluded = sum(ec['count'] for ec in self.ec_data)
        finals = compute_balanced_database_survival(self.db_progressions, total_screen_in, total_excluded)
        for db, fin in finals.items():
            self.db_progressions[db]['final'] = fin

        dot = _build_horizontal_slr_diagram(self.db_progressions, self.ec_data)
        
        # Check total hits in header
        self.assertIn("Total Initial Hits: 2,450", dot)
        self.assertIn("Passed to Screening: 200", dot)
        
        # Check IC funnel nodes
        self.assertIn("IC 1: <b>950 articles</b>", dot)
        self.assertIn("IC 2: <b>400 articles</b>", dot)
        self.assertIn("IC 3: <b>85 articles</b>", dot)
        
        # Check Phase 2 EC nodes
        self.assertIn("Total Excluded: 117", dot)
        self.assertIn("Final Yield: 83", dot)
        self.assertIn("- 60", dot)
        self.assertIn("- 40", dot)
        self.assertIn("- 17", dot)
        
        # Check final node
        self.assertIn("83<br/><font point-size=\"9\" color=\"#166534\"><b>FINAL INCLUDED</b></font>", dot)
        
        # Check right pills sum to 83
        for db, fin in finals.items():
            self.assertIn(f"{db}:<br/><b>{fin:,} included</b>", dot)

    def test_vertical_flowchart_dot_contains_exact_numbers(self):
        """Verify that vertical DOT output reflects the exact numbers."""
        total_screen_in = sum(d['ics'][-1][1] for d in self.db_progressions.values())
        total_excluded = sum(ec['count'] for ec in self.ec_data)
        finals = compute_balanced_database_survival(self.db_progressions, total_screen_in, total_excluded)
        for db, fin in finals.items():
            self.db_progressions[db]['final'] = fin

        dot = _build_vertical_slr_diagram(self.db_progressions, self.ec_data, self.user_ics, total_duplicates=15)
        
        # Total initial records identified
        self.assertIn("n = 2,450", dot)
        self.assertIn("Duplicates Removed: - 15", dot)
        
        # IC sequential survival
        self.assertIn("Surviving Records: n = 2,050", dot) # 950 + 710 + 390
        self.assertIn("Surviving Records: n = 900", dot)   # 400 + 320 + 180
        self.assertIn("Surviving Records: n = 200", dot)   # 85 + 65 + 50
        
        # Candidate pool
        self.assertIn("Candidate Studies Entering Screening Pool<br/><b>n = 185</b>", dot)
        
        # Final included
        self.assertIn("Final Studies Included in Systematic Literature Review<br/><b>n = 83</b>", dot)
        
        # Check breakdown
        for db, fin in finals.items():
            self.assertIn(f"{db}:<br/><b>{fin:,} studies</b>", dot)

    def test_edge_case_zero_exclusions(self):
        """When 0 exclusions occur, all studies survive into final."""
        zero_ec = [{'id': 'EC 1', 'title': 'None', 'count': 0, 'remaining': 200}]
        total_screen_in = sum(d['ics'][-1][1] for d in self.db_progressions.values())
        finals = compute_balanced_database_survival(self.db_progressions, total_screen_in, 0)
        self.assertEqual(sum(finals.values()), total_screen_in)
        for db, fin in finals.items():
            self.assertEqual(fin, self.db_progressions[db]['ics'][-1][1])

if __name__ == '__main__':
    unittest.main()
