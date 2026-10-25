"""Product search behavior for the Telegram shop catalog."""

from app.domain import catalog_search_service


def test_search_matches_service_and_offer_names_without_accents():
    offers = [
        {
            "id": 11,
            "service_name": "Télégram",
            "name": "Premium annuel",
            "description": "Compte individuel",
        },
        {
            "id": 12,
            "service_name": "Canva",
            "name": "Pro mensuel",
            "description": "Design et modèles",
        },
    ]

    assert [item["id"] for item in catalog_search_service.search(offers, "telegram annuel")] == [11]
    assert [item["id"] for item in catalog_search_service.search(offers, "design")] == [12]


def test_search_requires_every_word_and_limits_results():
    offers = [
        {"id": index, "service_name": "ChatGPT", "name": f"Team {index}"}
        for index in range(15)
    ]
    offers.append({"id": 99, "service_name": "ChatGPT", "name": "Plus"})

    matches = catalog_search_service.search(offers, "chatgpt team", limit=10)

    assert len(matches) == 10
    assert all("Team" in item["name"] for item in matches)


def test_empty_search_returns_no_products():
    assert catalog_search_service.search([{"id": 1, "name": "Canva"}], "   ") == []
