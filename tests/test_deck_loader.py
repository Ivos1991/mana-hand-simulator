from pathlib import Path

from mana_hand_simulator.deck_loader import load_card_config, load_deck, parse_deck_text


def test_load_deck(tmp_path: Path) -> None:
    path = tmp_path / "deck.txt"
    path.write_text("2 Swamp\n1 Sol Ring\n", encoding="utf-8")

    assert load_deck(path) == ["Swamp", "Swamp", "Sol Ring"]


def test_load_card_config(tmp_path: Path) -> None:
    path = tmp_path / "config.csv"
    path.write_text(
        "card_name,weight,type,is_land\n"
        "Swamp,0,land,true\n"
        "Sol Ring,3,premium_acceleration,false\n",
        encoding="utf-8",
    )

    config = load_card_config(path)

    assert config["Sol Ring"].weight == 3
    assert config["Sol Ring"].category == "premium_acceleration"
    assert config["Swamp"].is_land is True


def test_parse_moxfield_export_metadata_and_tags() -> None:
    text = (
        "1 Alpha Deathclaw (PIP) 91 #Removal\n"
        "1 Commercial District (PMKM) 259p *F*\n"
        "1 Kogla, the Titan Ape (PIKO) 162★ *F* #Removal\n"
        "1 Chainer, Nightmare Adept (PLST) MH2-289 #Reanimation\n"
        "1 Disciple of Freyalise / Garden of Freyalise (MH3) 250 #Draw\n"
        "7 Forest (M21) 274\n"
    )

    deck = parse_deck_text(text)

    assert deck.count("Forest") == 7
    assert "Alpha Deathclaw" in deck
    assert "Commercial District" in deck
    assert "Kogla, the Titan Ape" in deck
    assert "Chainer, Nightmare Adept" in deck
    assert "Disciple of Freyalise / Garden of Freyalise" in deck
