"""app/trend_charts.py::marker_status -- judged against the normal range,
for both "lower is better" and "higher is better" markers."""
import pytest

from app.trend_charts import marker_status, point_status


@pytest.mark.parametrize("values, low, high, expected", [
    # the real case that motivated this: ALT 86.2 -> 84.7 with norm <= 41 was
    # shown as "жақсарып келеді" by the old last-vs-previous rule
    ([86.2, 84.7], 0, 41, "🔴 нормадан тыс, өзгеріссіз"),
    ([43.8, 68.5, 59.8, 86.2], 0, 41, "🔴 нормадан тыс, нашарлап келеді"),
    ([120, 80], 0, 41, "🟡 нормадан тыс, жақсарып келеді"),
    ([30, 35], 0, 41, "🟢 қалыпты"),
    ([60, 35], 0, 41, "🟢 қалыпқа келді"),
    # albumin: HIGHER is better -- rising toward the norm is improvement
    ([24, 27.4], 35, 52, "🟡 нормадан тыс, жақсарып келеді"),
    ([30, 26], 35, 52, "🔴 нормадан тыс, нашарлап келеді"),
    ([50], 0, 41, "🔴 нормадан тыс"),
    ([10], None, None, "⚪ норма белгісіз"),
])
def test_marker_status(values, low, high, expected):
    assert marker_status(values, low, high) == expected


def test_point_status():
    assert point_status(84.7, 0, 41).startswith("🔴 нормадан жоғары (2.1 есе)")
    assert point_status(27.4, 35, 52) == "🔴 нормадан төмен"
    assert point_status(40, 35, 52) == "🟢 қалыпты"
