import os
import shutil
import filecmp
import unittest
from tempfile import TemporaryDirectory

from extractor.mapping import refine_triangulation
from tests.common import temp_dir_prefix


class TestRefineTriangulation(unittest.TestCase):

    def setUp(self):
        self.data_dir = os.path.join("tests", "data", "large")
        self.work_dir = TemporaryDirectory(prefix=temp_dir_prefix)
        self.settings = {
            "merge_threshold_image": 20,
            "merge_threshold_world": 1,
            "max_module_depth": -1,
            "max_num_modules": 300,
            "optimizer_steps": 10
        }
        mapping_root = os.path.join(self.data_dir, "mapping")
        
        # copy files into temporary directory as refining works in-place
        shutil.copytree(
            src=os.path.join(mapping_root), 
            dst=os.path.join(self.work_dir.name, "mapping")
        )

        # where to load files with desired output format from
        self.ground_truth_dir = mapping_root

    def test_run(self):
        mapping_root = os.path.join(self.work_dir.name, "mapping")
        refine_triangulation.run(
            mapping_root, 
            **self.settings
        )
        
        # check if outputs equal ground truth
        file_names = [
            "modules_refined.pkl",
            "module_geolocations_refined.geojson",
        ]

        for file_name in file_names:
            self.assertTrue(
                filecmp.cmp(
                    os.path.join(mapping_root, file_name), 
                    os.path.join(self.ground_truth_dir, file_name), 
                    shallow=False
                ),
                "{} differs from ground truth".format(file_name)
            )
        

    def tearDown(self):
        self.work_dir.cleanup()