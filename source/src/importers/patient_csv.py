from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from src.error_messages import describe_os_error
from src.patient_fields import DEFAULT_INTERVENTION_MINUTES, normalize_diagnosis


class PatientCsvError(ValueError):
    """Errore di lettura o formato del CSV."""


@dataclass(frozen=True, slots=True)
class PatientCsvResult:
    """Risultato dell'importazione CSV."""

    rows: tuple[dict[str, str], ...]
    delimiter: str
    source_format: str
    warnings: tuple[str, ...]


_ALIASES = {
    "nome": ("nome",),
    "cognome": ("cognome",),
    "codice_diagnosi": ("codice_diagnosi", "codice_diagnosi_icd9"),
    "descrizione_diagnosi": (
        "descrizione_diagnosi",
        "diagnosi_descrittiva",
        "diagnosi_icd9",
        "diagnosi",
    ),
    "codice_intervento": ("codice_intervento", "codice_procedura"),
    "descrizione_intervento": (
        "descrizione_intervento",
        "intervento_procedura_icd9",
        "procedura",
    ),
    "tipo_chirurgia": ("tipo_chirurgia", "tipo_chir"),
    "complessita": ("complessita",),
    "urgenza": ("urgenza", "priorita", "priorit", "classe_priorita"),
    "durata_intervento": ("durata_intervento", "durata", "durata_minuti"),
}

_TRACKCARE_MARKERS = {
    "idpaziente",
    "numero_in_lista_di_attesa",
    "diagnosi_icd9",
    "intervento_procedura_icd9",
    "stato_lista",
}


def normalize_header(value: str) -> str:
    """Normalizza un'intestazione CSV per il confronto."""

    without_replacement = value.replace("ï¿½", "").replace("\ufffd", "")
    decomposed = unicodedata.normalize("NFKD", without_replacement)
    ascii_like = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", ascii_like.casefold()).strip("_")


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise PatientCsvError("Il file non è codificato in UTF-8 o Windows-1252.")


def _detect_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        counts = {delimiter: sample.count(delimiter) for delimiter in (",", ";", "\t", "|")}
        delimiter = max(counts, key=counts.get)
        if counts[delimiter] == 0:
            raise PatientCsvError(
                "Non è stato possibile riconoscere il separatore del CSV."
            ) from None
        return delimiter


def _first_value(row: dict[str, str], aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        value = row.get(alias, "").strip()
        if value:
            return value
    return ""


def _code_from_description(description: str) -> str:
    match = re.search(r"\(([A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*)\)\s*$", description)
    return match.group(1) if match else ""


def _remove_terminal_code(description: str, code: str) -> str:
    if not description or not code:
        return description
    return re.sub(rf"\s*\({re.escape(code)}\)\s*$", "", description).strip()


def _map_urgency(value: str) -> str:
    normalized = normalize_header(value)
    direct = {"alta": "Alta", "media": "Media", "bassa": "Bassa"}
    if normalized in direct:
        return direct[normalized]
    match = re.fullmatch(r"(?:classe_?)?([abcd])(?:_.*)?", normalized)
    if not match:
        return "Da classificare"
    return {"a": "Alta", "b": "Media", "c": "Bassa", "d": "Bassa"}[match.group(1)]


def split_procedure_fields(value: str) -> list[str]:
    """Split procedure lists, retaining empty positions between semicolons."""
    return [part.strip() for part in value.split(";")] if value.strip() else []


def build_csv_interventions(
    codes: str, descriptions: str, durations: str
) -> list[dict[str, str | int]]:
    """Build aligned procedures with positive integer durations in minutes.

    A single duration is the total; a duration list must match the procedure count.
    Raise PatientCsvError for invalid or inconsistent durations.
    """
    code_values = split_procedure_fields(codes)
    description_values = split_procedure_fields(descriptions)
    count = max(len(code_values), len(description_values), 1)
    duration_values = []
    for value in durations.split(";"):
        match = re.fullmatch(r"([0-9]+)(?:\s*min)?", value.strip(), flags=re.IGNORECASE)
        if not match or not 0 < int(match.group(1)) <= 10080:
            raise PatientCsvError("La durata deve essere un intero positivo in minuti.")
        duration_values.append(int(match.group(1)))
    if len(duration_values) == 1:
        if duration_values[0] < count:
            raise PatientCsvError("La durata totale è inferiore al numero di interventi.")
        per_procedure, remainder = divmod(duration_values[0], count)
        duration_values = [per_procedure + (index < remainder) for index in range(count)]
    elif len(duration_values) != count:
        raise PatientCsvError("Il numero di durate deve corrispondere agli interventi.")
    return [
        {
            "codice": code_values[index] if index < len(code_values) else "",
            "descrizione": description_values[index] if index < len(description_values) else "",
            "durata": duration_values[index],
        }
        for index in range(count)
    ]


def read_patient_csv(path: str | Path) -> PatientCsvResult:
    """Legge un CSV nativo o TrackCare e normalizza le righe importate."""

    csv_path = Path(path)
    try:
        text = _read_text(csv_path)
    except OSError as error:
        raise PatientCsvError(
            f"Impossibile leggere il file: {describe_os_error(error)}"
        ) from error

    delimiter = _detect_delimiter(text[:8192])
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    try:
        fieldnames = reader.fieldnames
    except csv.Error as error:
        raise PatientCsvError("La riga delle intestazioni CSV non è valida.") from error
    if not fieldnames:
        raise PatientCsvError("Il file CSV non contiene una riga di intestazione.")

    normalized_headers = [normalize_header(header or "") for header in fieldnames]
    if not any(normalized_headers):
        raise PatientCsvError("Le intestazioni del CSV non sono riconoscibili.")
    missing = [field for field in ("nome", "cognome") if field not in normalized_headers]
    if missing:
        raise PatientCsvError("Il CSV non contiene le colonne richieste: " + ", ".join(missing))
    nonempty_headers = [header for header in normalized_headers if header]
    if len(set(nonempty_headers)) != len(nonempty_headers):
        raise PatientCsvError("Il CSV contiene intestazioni duplicate.")

    source_format = "TrackCare" if set(normalized_headers) & _TRACKCARE_MARKERS else "Scadenziario"
    normalized_rows: list[dict[str, str]] = []
    try:
        source_rows = list(reader)
    except csv.Error as error:
        raise PatientCsvError(f"CSV non valido vicino alla riga {reader.line_num}.") from error
    unclassified_urgency_count = 0
    missing_duration_count = 0
    for row_number, source_row in enumerate(source_rows, 2):
        if None in source_row:
            raise PatientCsvError(
                f"La riga {row_number} contiene più campi delle intestazioni. "
                "Racchiudi tra virgolette i valori che contengono il separatore."
            )
        row = {
            normalize_header(header or ""): (value or "").strip()
            for header, value in source_row.items()
            if header is not None
        }
        if not any(row.values()):
            continue

        diagnosis_description = _first_value(row, _ALIASES["descrizione_diagnosi"])
        diagnosis_code = _first_value(row, _ALIASES["codice_diagnosi"])
        diagnosis_code, diagnosis_description, _ = normalize_diagnosis(
            diagnosis_code, diagnosis_description
        )

        intervention_description = _first_value(row, _ALIASES["descrizione_intervento"])
        intervention_code = _first_value(row, _ALIASES["codice_intervento"])
        descriptions = split_procedure_fields(intervention_description)
        codes = split_procedure_fields(intervention_code)
        count = max(len(descriptions), len(codes))
        descriptions += [""] * (count - len(descriptions))
        codes += [""] * (count - len(codes))
        for index, description in enumerate(descriptions):
            codes[index] = codes[index] or _code_from_description(description)
            descriptions[index] = _remove_terminal_code(description, codes[index])
        intervention_code = ";".join(codes)
        intervention_description = ";".join(descriptions)
        urgency = _map_urgency(_first_value(row, _ALIASES["urgenza"]))
        if urgency == "Da classificare":
            unclassified_urgency_count += 1
        duration = _first_value(row, _ALIASES["durata_intervento"])
        if not duration:
            missing_duration_count += 1

        normalized_rows.append(
            {
                "nome": _first_value(row, _ALIASES["nome"]),
                "cognome": _first_value(row, _ALIASES["cognome"]),
                "codice_diagnosi": diagnosis_code,
                "descrizione_diagnosi": diagnosis_description,
                "codice_intervento": intervention_code,
                "descrizione_intervento": intervention_description,
                "tipo_chirurgia": _first_value(row, _ALIASES["tipo_chirurgia"])
                or "Da classificare",
                "complessita": _first_value(row, _ALIASES["complessita"]) or "Da classificare",
                "urgenza": urgency,
                "durata_intervento": duration or str(DEFAULT_INTERVENTION_MINUTES),
            }
        )

    warnings: list[str] = []
    if unclassified_urgency_count:
        warnings.append(
            f"Urgenza assente o non riconosciuta in {unclassified_urgency_count} righe: "
            "impostata su 'Da classificare'."
        )
    header_set = set(normalized_headers)
    if not header_set.intersection(_ALIASES["tipo_chirurgia"]):
        warnings.append("Tipo chirurgia assente: impostato su 'Da classificare'.")
    if not header_set.intersection(_ALIASES["complessita"]):
        warnings.append("Complessità assente: impostata su 'Da classificare'.")
    if missing_duration_count:
        warnings.append("Durata assente: impostata a 90 minuti e modificabile in anteprima.")

    return PatientCsvResult(
        rows=tuple(normalized_rows),
        delimiter=delimiter,
        source_format=source_format,
        warnings=tuple(warnings),
    )
