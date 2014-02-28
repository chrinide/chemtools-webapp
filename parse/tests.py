import os
import zipfile
import csv

from django.conf import settings
from django.test import Client, TestCase
from django.core.urlresolvers import reverse

import views
from project.utils import StringIO


class MainPageTestCase(TestCase):
    def setUp(self):
        self.client = Client()

    def test_index(self):
        response = self.client.get(reverse(views.upload_data))
        self.assertEqual(response.status_code, 200)

    def test_log_parse(self):
        test_path = os.path.join(settings.MEDIA_ROOT, "tests")
        with open(os.path.join(test_path, "A_TON_A_A.log"), 'r') as f:
            data = {
                "myfiles": f,
                "option": "logparse",
            }
            response = self.client.post(reverse(views.upload_data), data)
            self.assertEqual(response.status_code, 200)
            with StringIO(response.content) as f:
                reader = csv.reader(f, delimiter=',', quotechar='"')
                expected = ["A_TON_A_A.log", "A_TON_A_A",
                            "A_TON_A_A_n1_m1_x1_y1_z1",
                            "opt B3LYP/6-31g(d) geom=connectivity",
                            "-6.46079886952",
                            "-1.31975211714",
                            "41",
                            "0.0006",
                            "-567.1965205",
                            "---",
                            "0.35"]
                lines = [x for x in reader]
                results = lines[1][:3] + lines[1][4:]
                self.assertEqual(results, expected)

    def test_gjf_reset(self):
        base = os.path.join(settings.MEDIA_ROOT, "tests", "A_TON_A_A")
        with open(base + ".log", 'r') as log, open(base + ".gjf", 'r') as gjf:
            data = {
                "myfiles": log,
                "option": "gjfreset",
            }
            response = self.client.post(reverse(views.upload_data), data)
            self.assertEqual(response.status_code, 200)
            with StringIO(response.content) as f:
                with zipfile.ZipFile(f, "r") as zfile:
                    with zfile.open("A_TON_A_A.gjf") as f2:
                        self.assertEqual(f2.read(), gjf.read())

    def test_gjf_reset_td(self):
        base = os.path.join(settings.MEDIA_ROOT, "tests", "A_TON_A_A")
        log_path = base + ".log"
        gjf_path = base + "_TD.gjf"
        with open(log_path, 'r') as log, open(gjf_path, 'r') as gjf:
            data = {
                "myfiles": log,
                "option": "gjfreset",
                "reset_td": True,
            }
            response = self.client.post(reverse(views.upload_data), data)
            self.assertEqual(response.status_code, 200)
            with StringIO(response.content) as f:
                with zipfile.ZipFile(f, "r") as zfile:
                    with zfile.open("A_TON_A_A_TD.gjf") as f2:
                        self.assertEqual(f2.read(), gjf.read())

    def test_gjf_reset_fail(self):
        base = os.path.join(settings.MEDIA_ROOT, "tests", "A_TON_A_A")
        with open(base + ".gjf", 'r') as gjf:
            data = {
                "myfiles": gjf,
                "option": "gjfreset",
            }
            response = self.client.post(reverse(views.upload_data), data)
            self.assertEqual(response.status_code, 200)
            with StringIO(response.content) as f:
                with zipfile.ZipFile(f, "r") as zfile:
                    with zfile.open("errors.txt") as f2:
                        msg = "A_TON_A_A - The log file was invalid"
                        self.assertEqual(f2.read(), msg)

    def test_data_parse(self):
        datatxt = os.path.join(settings.MEDIA_ROOT, "tests", "data.txt")
        outputtxt = os.path.join(settings.MEDIA_ROOT, "tests", "output.txt")
        with open(datatxt, 'r') as txt:
            data = {
                "myfiles": txt,
                "option": "dataparse",
            }
            response = self.client.post(reverse(views.upload_data), data)
            self.assertEqual(response.status_code, 200)
            with StringIO(response.content) as f, open(outputtxt, 'r') as out:
                with zipfile.ZipFile(f, "r") as zfile:
                    with zfile.open("output.txt") as f2:
                        self.assertEqual(f2.read(), out.read())

    def test_data_parse_set(self):
        for filename in ["CON.tar.gz", "TON.tar.bz2"]:
            filepath = os.path.join(settings.MEDIA_ROOT, "tests", filename)
            with open(filepath, 'r') as zfile:
                data = {
                    "myfiles": zfile,
                    "option": "dataparse",
                }
                response = self.client.post(reverse(views.upload_data), data)
                self.assertEqual(response.status_code, 200)
                with StringIO(response.content) as f:
                    with zipfile.ZipFile(f, "r") as zfile2:
                        with zfile2.open("output.txt") as f2:
                            self.assertIn("Errors (0)", f2.read())

    def test_data_parse_multi_set(self):
        filepath = os.path.join(settings.MEDIA_ROOT, "tests", "both.zip")
        with open(filepath, 'r') as zfile:
            data = {
                "myfiles": zfile,
                "option": "dataparse",
            }
            response = self.client.post(reverse(views.upload_data), data)
            self.assertEqual(response.status_code, 200)
            with StringIO(response.content) as f:
                with zipfile.ZipFile(f, "r") as zfile2:
                    for folder in ["CON__TD/", "TON__TD/"]:
                        with zfile2.open(folder + "output.txt") as f2:
                            self.assertIn("Errors (0)", f2.read())

    def test_data_parse_log(self):
        test_path = os.path.join(settings.MEDIA_ROOT, "tests")
        with open(os.path.join(test_path, "A_TON_A_A.log"), 'r') as f:
            data = {
                "myfiles": f,
                "option": "dataparse",
            }
            response = self.client.post(reverse(views.upload_data), data)
        self.assertEqual(response.status_code, 200)

    def test_parse_without_data(self):
        data = {
            "myfiles": '',
            "option": "dataparse",
        }
        response = self.client.post(reverse(views.upload_data), data)
        self.assertEqual(response.status_code, 200)
