import unittest

from monitor import Project, extract_registered_projects, infer_project_type


class MonitorTests(unittest.TestCase):
    def test_extracts_portal_row(self):
        page = """
        <table id="compliant_hearing"><tbody><tr>
          <td>1</td><td>HRERA-PKL-FBD-914-2026</td>
          <td><a href="/view_project/searchprojectDetail/3599">RERA-PKL-2033-2026</a></td>
          <td>AMOLIK CONCORDIA LIVING- I</td><td>LOGERS REAL ESTATE BUILDERS LLP</td>
          <td>SECTOR-97, FARIDABAD</td><td>FARIDABAD</td><td>HRERA</td>
          <td><a href="/view_project/project_preview_open/3599">View</a></td>
          <td>17/03/2031</td>
        </tr>""" + "".join(
            f"<tr><td>{i}</td><td>REG-{i}</td><td>ID-{i}</td><td>N</td><td>B</td><td>L</td><td>C</td><td>R</td><td></td><td>D</td></tr>"
            for i in range(2, 502)
        ) + "</tbody></table>"
        projects = extract_registered_projects(page)
        self.assertEqual(projects[0].city, "FARIDABAD")
        self.assertTrue(projects[0].priority)
        self.assertTrue(projects[0].detail_url.endswith("/3599"))

    def test_type_inference_uses_strong_phrase(self):
        p = Project("R1", "P1", "Affordable Plotted Colony", "B", "Sector 1", "GURUGRAM", "HRERA", "", "", "")
        self.assertEqual(infer_project_type(p, None), "Residential – Plotted Development")


if __name__ == "__main__":
    unittest.main()
