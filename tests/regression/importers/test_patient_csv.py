from __future__ import annotations

from pathlib import Path

import pytest

from src.importers.patient_csv import (
    PatientCsvError,
    build_csv_interventions,
    read_patient_csv,
)


def test_trackcare_semicolon_export_is_normalized(tmp_path: Path) -> None:
    source = tmp_path / "trackcare.csv"
    source.write_text(
        "Nome;Cognome;Priorit�;Diagnosi ICD9;codice diagnosi;"
        "Intervento/procedura ICD9; codice intervento\n"
        "Ada;Test;Classe A;Descrizione sintetica (433.10);433.10;"
        "Procedura sintetica (38.12);38.12\n",
        encoding="utf-8",
    )

    result = read_patient_csv(source)

    assert result.source_format == "TrackCare"
    assert result.delimiter == ";"
    assert len(result.rows) == 1
    assert result.rows[0] == {
        "nome": "Ada",
        "cognome": "Test",
        "codice_diagnosi": "433.10",
        "descrizione_diagnosi": "Descrizione sintetica",
        "codice_intervento": "38.12",
        "descrizione_intervento": "Procedura sintetica",
        "tipo_chirurgia": "Da classificare",
        "complessita": "Da classificare",
        "urgenza": "Alta",
        "durata_intervento": "90",
    }
    assert len(result.warnings) == 3


def test_native_csv_keeps_explicit_values_and_multiple_interventions(
    tmp_path: Path,
) -> None:
    source = tmp_path / "native.csv"
    source.write_text(
        "nome,cognome,diagnosi,codice_intervento,descrizione_intervento,"
        "tipo_chirurgia,complessita,urgenza,durata_intervento\n"
        'Ada,Test,Diagnosi sintetica,"11.1;22.2","Prima;Seconda",'
        'Aperta,Media,Bassa,"30;45"\n',
        encoding="utf-8",
    )

    result = read_patient_csv(source)

    assert result.source_format == "Scadenziario"
    assert result.delimiter == ","
    assert result.rows[0]["descrizione_diagnosi"] == "Diagnosi sintetica"
    assert result.rows[0]["durata_intervento"] == "30;45"
    assert result.warnings == ()


def test_unstructured_text_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "invalid.csv"
    source.write_text("testo senza separatore", encoding="utf-8")

    with pytest.raises(PatientCsvError, match="separatore"):
        read_patient_csv(source)


@pytest.mark.parametrize("header", ["Priorità", "Priorit�", "Prioritï¿½", "urgenza"])
@pytest.mark.parametrize("encoding", ["utf-8-sig", "cp1252"])
def test_priority_headers_and_encodings(tmp_path: Path, header: str, encoding: str) -> None:
    if encoding == "cp1252" and "�" in header:
        pytest.skip("The replacement character cannot be encoded in Windows-1252")
    path = tmp_path / "priority.csv"
    path.write_text(f"Nome;Cognome;{header}\nNome;Demo;Classe A\n", encoding=encoding)
    assert read_patient_csv(path).rows[0]["urgenza"] == "Alta"


@pytest.mark.parametrize("value", ["", "Sconosciuta", "Non urgente", "12"])
def test_unknown_priority_is_not_assigned_a_clinical_class(tmp_path: Path, value: str) -> None:
    path = tmp_path / "unknown.csv"
    path.write_text(f"Nome;Cognome;Priorità\nNome;Demo;{value}\n", encoding="utf-8")
    result = read_patient_csv(path)
    assert result.rows[0]["urgenza"] == "Da classificare"
    assert any("Urgenza assente" in warning for warning in result.warnings)


def test_diagnosis_code_and_multiple_procedures_preserve_positions(tmp_path: Path) -> None:
    path = tmp_path / "multiple.csv"
    path.write_text(
        "Nome,Cognome,Diagnosi ICD9,codice intervento,Intervento/procedura ICD9\n"
        'Nome,Demo,433.10,";22.2;","Prima (11.1);Seconda;Terza (33.3)"\n',
        encoding="utf-8",
    )
    row = read_patient_csv(path).rows[0]
    assert row["codice_diagnosi"] == "433.10"
    assert row["descrizione_diagnosi"] == ""
    assert row["codice_intervento"] == "11.1;22.2;33.3"
    assert row["descrizione_intervento"] == "Prima;Seconda;Terza"
    interventions = build_csv_interventions("11.1;;33.3", "Prima;Seconda;Terza", "30;40;50")
    assert [item["codice"] for item in interventions] == ["11.1", "", "33.3"]
    assert [item["durata"] for item in interventions] == [30, 40, 50]


def test_csv_preserves_quoted_multiline_descriptions(tmp_path: Path) -> None:
    path = tmp_path / "multiline.csv"
    path.write_text('Nome,Cognome,diagnosi\nNome,Demo,"Prima riga\nSeconda riga"\n')
    assert read_patient_csv(path).rows[0]["descrizione_diagnosi"] == "Prima riga\nSeconda riga"


@pytest.mark.parametrize(
    "source",
    [
        "Foo,Bar\nUno,Due\n",
        "Nome,Nome,Cognome\nUno,Due,Tre\n",
        "Nome,Cognome\nUno,Due,Tre\n",
        'Nome,Cognome\nUno,"Due\n',
    ],
)
def test_invalid_csv_structure_has_an_explicit_error(tmp_path: Path, source: str) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(source, encoding="utf-8")
    with pytest.raises(PatientCsvError):
        read_patient_csv(path)


@pytest.mark.parametrize("duration", ["0", "-2", "2.5", "test", "10;0", "10;20;30", "1"])
def test_invalid_durations_are_not_replaced_with_defaults(duration: str) -> None:
    with pytest.raises(PatientCsvError):
        build_csv_interventions("11;22", "Prima;Seconda", duration)
