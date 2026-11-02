import unittest

from shared.kanji_web import build_graph


def row(subject_id, object_type, level, characters, meaning, position, components=(), similar=()):
    return {
        "id": subject_id,
        "type": object_type,
        "level": level,
        "characters": characters,
        "meaning": meaning,
        "reading": None,
        "lesson_position": position,
        "component_ids": list(components),
        "similar_ids": list(similar),
    }


class KanjiWebTests(unittest.TestCase):
    def test_component_edges_and_outside_parents(self):
        rows = [
            row(1, "radical", 1, "人", "person", 1),
            row(10, "kanji", 5, "休", "rest", 3, components=[1]),
            row(20, "vocabulary", 5, "休む", "to rest", 4, components=[10]),
        ]
        graph = build_graph(rows, stages={10: 5, 20: 6}, weak=set(), level=5)
        radical = graph["lanes"]["radical"][0]
        kanji = graph["lanes"]["kanji"][0]
        self.assertTrue(radical["outside"])
        self.assertFalse(kanji["outside"])
        self.assertEqual(radical["label"], "人")
        pairs = {(edge["from"], edge["to"], edge["kind"]) for edge in graph["edges"]}
        self.assertIn((10, 1, "component"), pairs)
        self.assertIn((20, 10, "component"), pairs)

    def test_image_radical_uses_its_meaning_as_the_label(self):
        rows = [row(3, "radical", 2, None, "ground", 1)]
        graph = build_graph(rows, {}, set(), 2)
        self.assertEqual(graph["lanes"]["radical"][0]["label"], "ground")
        self.assertIsNone(graph["lanes"]["radical"][0]["characters"])

    def test_weak_links_rank_by_how_many_words_depend_on_them(self):
        rows = [
            row(1, "kanji", 3, "人", "person", 1),
            row(2, "kanji", 3, "日", "day", 2),
        ]
        for index in range(6):
            rows.append(row(100 + index, "vocabulary", 3, f"w{index}", "word", index, components=[1]))
        rows.append(row(200, "vocabulary", 3, "today", "today", 9, components=[2]))
        graph = build_graph(rows, stages={1: 3}, weak={1, 2}, level=3)
        self.assertTrue(graph["lanes"]["kanji"][0]["weak"] or graph["lanes"]["kanji"][1]["weak"])
        self.assertEqual(graph["weak_links"][0]["id"], 1)
        self.assertEqual(graph["weak_links"][0]["dependents"], 6)
        self.assertEqual(graph["weak_links"][1]["dependents"], 1)
        self.assertLessEqual(len(graph["weak_links"]), 3)

    def test_relearn_stage_is_weak_without_being_passed_in(self):
        rows = [row(8, "kanji", 4, "大", "big", 1)]
        graph = build_graph(rows, stages={8: 3}, weak=set(), level=4)
        self.assertTrue(graph["lanes"]["kanji"][0]["weak"])
        self.assertEqual(graph["lanes"]["kanji"][0]["bucket"], "relearn")

    def test_barycentric_order_follows_components(self):
        rows = [
            row(1, "radical", 4, "A", "a", 1),
            row(2, "radical", 4, "B", "b", 10),
            row(11, "kanji", 4, "K1", "k1", 1, components=[2]),
            row(12, "kanji", 4, "K2", "k2", 2, components=[1]),
            row(21, "vocabulary", 4, "V1", "v1", 1, components=[11]),
            row(22, "vocabulary", 4, "V2", "v2", 2, components=[12]),
        ]
        graph = build_graph(rows, {}, set(), 4)
        self.assertEqual([node["id"] for node in graph["lanes"]["radical"]], [1, 2])
        self.assertEqual([node["id"] for node in graph["lanes"]["kanji"]], [12, 11])
        self.assertEqual([node["id"] for node in graph["lanes"]["vocabulary"]], [22, 21])

    def test_similar_edges_are_one_per_pair(self):
        rows = [
            row(11, "kanji", 4, "未", "not yet", 1, similar=[12]),
            row(12, "kanji", 4, "末", "end", 2, similar=[11]),
        ]
        graph = build_graph(rows, {}, set(), 4)
        similar = [edge for edge in graph["edges"] if edge["kind"] == "similar"]
        self.assertEqual(len(similar), 1)
        self.assertEqual(similar[0]["from"], 11)
        self.assertEqual(similar[0]["to"], 12)


if __name__ == "__main__":
    unittest.main()
