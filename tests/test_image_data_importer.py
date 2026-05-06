import unittest

import app
import image_data_importer as importer


class ImageDataImporterTests(unittest.TestCase):
    def test_parse_strikeout_odds_text(self):
        text = """
        Max Fried 3+ Strikeouts -4500
        Max Fried 4+ Strikeouts -1000
        Max Fried 7+ Strikeouts +148
        """

        rows = importer.parse_strikeout_odds_text(text)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["Player"], "Max Fried")
        self.assertEqual(rows[0]["Line"], "2.5")
        self.assertEqual(rows[2]["Odds"], "+148")

    def test_parse_daily_strikeouts_text(self):
        text = "Matthew Boyd L 18 33.33% 21.95% 21.95% 13 29.76% ARI 18.86% 19.17% 20.47%"

        rows = importer.parse_daily_strikeouts_text(text)

        self.assertEqual(rows[0]["Pitcher"], "Matthew Boyd")
        self.assertEqual(rows[0]["K%"], "33.33%")
        self.assertEqual(rows[0]["Opponent"], "ARI")
        self.assertEqual(rows[0]["Opp K%"], "18.86%")

    def test_parse_hr_sheet_text(self):
        text = "Chase Burns 34 5 1.32 4 1 39.3% 40.7% 9.3% PIT"

        rows = importer.parse_hr_sheet_text(text)

        self.assertEqual(rows[0]["Pitcher"], "Chase Burns")
        self.assertEqual(rows[0]["HR"], "5")
        self.assertEqual(rows[0]["Barrel%"], "9.3%")

    def test_app_ocr_parse_payload_returns_csv(self):
        payload = app.parse_ocr_payload({"type": "strikeout-odds", "text": "Max Fried 7+ Strikeouts +148"})

        self.assertEqual(payload["count"], 1)
        self.assertIn("Pitcher Strikeouts", payload["csv"])


if __name__ == "__main__":
    unittest.main()
