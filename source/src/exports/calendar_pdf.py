"""Esportazione dei calendari in PDF.

Il calendario è disegnato con ``QPainter`` su A4 orizzontale: un giorno per colonna e
un'attività per riga, come a schermo. La griglia occupa tutta l'area stampabile e i giorni
non lavorativi hanno colonne strette. I testi non vengono mai tagliati: il carattere è il
più grande con cui tutti entrano nella colonna e un testo ancora troppo largo viene
compresso in orizzontale. Se le righe non entrano in una pagina proseguono nella
successiva, con titolo e intestazione dei giorni ripetuti.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QPen,
)

_RESOLUTION_DPI = 144
_MARGIN_MM = 8
_TABLE_WIDTH_MM = 297 - 2 * _MARGIN_MM
"""Larghezza utile di un A4 orizzontale."""
_LABEL_COLUMN_MM = 24
_REST_COLUMN_MM = 5
_TITLE_HEIGHT_MM = 13
_HEADER_HEIGHT_MM = 9
_FOOTER_GAP_MM = 1.5
_CELL_PADDING_MM = 0.8
_MIN_ROW_MM = 9
_MAX_ROW_MM = 28

_MAX_FONT_PT = 10.0
_MIN_FONT_PT = 6.0
_FONT_STEP_PT = 0.25
_MIN_TEXT_SCALE = 0.8
"""Compressione orizzontale massima ammessa nella scelta del carattere."""
_FONT_FAMILY = "Helvetica"

_EMPTY_VALUES = frozenset({"", "-"})
_TEXT_COLOR = QColor("#1e293b")
_LABEL_TEXT_COLOR = QColor("#334155")
_MUTED_COLOR = QColor("#64748b")
_GRID_COLOR = QColor("#cbd5e1")
_HEADER_BACKGROUND = QColor("#e2e8f0")
_REST_DAY_BACKGROUND = QColor("#f1f5f9")


class CalendarPdfError(RuntimeError):
    """Errore durante la creazione del PDF."""


@dataclass(frozen=True, slots=True)
class CalendarPdfRow:
    """Attività del calendario: una riga del PDF, con un valore per giorno.

    ``value_colors`` colora valori specifici (es. il tipo di guardia).
    """

    label: str
    values: tuple[str, ...]
    background: str = "#ffffff"
    value_colors: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CalendarPdfDocument:
    """Dati necessari per creare il calendario PDF.

    ``column_headers`` sono i giorni (``"<numero> <giorno>"``, stampati su due righe);
    ``rest_columns`` gli indici dei giorni non lavorativi (colonne strette);
    ``stacked_names`` stampa i nomi ``Cognome N.`` su due righe (cognome, iniziale);
    ``footnote`` e ``legend`` sono stampate sotto la tabella.
    """

    title: str
    period: str
    column_headers: tuple[str, ...]
    rows: tuple[CalendarPdfRow, ...]
    legend: tuple[tuple[str, str], ...] = ()
    footnote: str = ""
    rest_columns: frozenset[int] = frozenset()
    stacked_names: bool = False

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.period.strip():
            raise ValueError("Il PDF richiede un titolo e un periodo.")
        if not self.column_headers:
            raise ValueError("Il PDF richiede almeno una colonna del calendario.")
        expected = len(self.column_headers)
        if any(len(row.values) != expected for row in self.rows):
            raise ValueError("Ogni riga del PDF deve avere lo stesso numero di colonne.")
        if any(not 0 <= index < expected for index in self.rest_columns):
            raise ValueError("Le colonne dei giorni non lavorativi devono esistere nel PDF.")


def column_fractions(document: CalendarPdfDocument) -> tuple[float, ...]:
    """Frazione della larghezza della tabella per ogni colonna: etichette, poi i giorni.

    I giorni non lavorativi hanno una colonna stretta; se tutti i giorni sono non
    lavorativi le colonne restano uguali.
    """

    days = len(document.column_headers)
    rest = len(document.rest_columns)
    workdays = days - rest
    available = _TABLE_WIDTH_MM - _LABEL_COLUMN_MM
    if workdays == 0:
        widths = [available / days] * days
    else:
        work_width = (available - _REST_COLUMN_MM * rest) / workdays
        widths = [
            _REST_COLUMN_MM if index in document.rest_columns else work_width
            for index in range(days)
        ]
    return tuple(width / _TABLE_WIDTH_MM for width in (_LABEL_COLUMN_MM, *widths))


def name_lines(value: str, *, stacked: bool) -> tuple[str, ...]:
    """Righe con cui stampare un valore: ``Cognome N.`` diventa cognome e iniziale."""

    text = value.strip()
    if stacked:
        surname, _, initial = text.rpartition(" ")
        if surname and initial.endswith(".") and len(initial) <= 3:
            return (surname, initial)
    return (text,)


def fit_font_size(
    texts: Iterable[str],
    *,
    room: float,
    measure: Callable[[str, float], float],
    fits_height: Callable[[float], bool] = lambda _size: True,
) -> float:
    """Carattere più grande (in punti) con cui ogni testo entra in ``room``.

    Ogni testo può essere compresso in orizzontale fino a ``_MIN_TEXT_SCALE``; sotto
    ``_MIN_FONT_PT`` non si scende (il disegno comprime ancora, ma non taglia mai).
    """

    candidates = [text for text in texts if text]
    size = _MAX_FONT_PT
    while size > _MIN_FONT_PT:
        if fits_height(size) and all(
            measure(text, size) * _MIN_TEXT_SCALE <= room for text in candidates
        ):
            return size
        size -= _FONT_STEP_PT
    return _MIN_FONT_PT


def _millimeters(value: float) -> float:
    return value / 25.4 * _RESOLUTION_DPI


def _font(size: float, *, bold: bool = False) -> QFont:
    font = QFont(_FONT_FAMILY)
    font.setPointSizeF(size)
    font.setBold(bold)
    return font


def _tint(color: str, amount: float = 0.55) -> QColor:
    base = QColor(color)
    channels = (base.red(), base.green(), base.blue())
    return QColor(*(round(value + (255 - value) * amount) for value in channels))


class _Renderer:
    """Disegna il documento pagina per pagina su un ``QPdfWriter``."""

    def __init__(self, writer: QPdfWriter, document: CalendarPdfDocument) -> None:
        self._writer = writer
        self._document = document
        page = writer.pageLayout().paintRectPixels(writer.resolution())
        self._width = float(page.width())
        self._height = float(page.height())
        self._padding = _millimeters(_CELL_PADDING_MM)
        fractions = column_fractions(document)
        self._label_width = fractions[0] * self._width
        self._column_widths = [fraction * self._width for fraction in fractions[1:]]

    def _metrics(self, font: QFont) -> QFontMetricsF:
        return QFontMetricsF(font, self._writer)

    def _footer_lines(self) -> list[str]:
        lines = [self._document.footnote] if self._document.footnote else []
        if self._document.legend:
            lines.append(
                "Legenda: "
                + " · ".join(f"{initials} = {name}" for initials, name in self._document.legend)
            )
        return lines

    def _footer_height(self) -> float:
        metrics = self._metrics(_font(7))
        text = "\n".join(self._footer_lines()) or "Pagina"
        bounds = metrics.boundingRect(
            QRectF(0, 0, self._width * 0.85, 10_000), Qt.TextFlag.TextWordWrap, text
        )
        return bounds.height() + _millimeters(_FOOTER_GAP_MM)

    def _body_room(self) -> float:
        top = _millimeters(_TITLE_HEIGHT_MM) + _millimeters(_HEADER_HEIGHT_MM)
        return self._height - top - self._footer_height()

    def pages(self) -> list[range]:
        """Righe di ogni pagina: quante ne entrano con l'altezza minima di riga."""

        rows = len(self._document.rows)
        per_page = max(1, int(self._body_room() // _millimeters(_MIN_ROW_MM)))
        pages = [range(start, min(start + per_page, rows)) for start in range(0, rows, per_page)]
        return pages or [range(0)]

    def _row_height(self, rows_on_page: int) -> float:
        if rows_on_page == 0:
            return 0.0
        return min(self._body_room() / rows_on_page, _millimeters(_MAX_ROW_MM))

    def _workday_room(self) -> float:
        workdays = [
            width
            for index, width in enumerate(self._column_widths)
            if index not in self._document.rest_columns
        ] or self._column_widths
        return min(workdays) - 2 * self._padding

    def _value_font_size(self, row_height: float) -> float:
        texts = [
            line
            for row in self._document.rows
            for value in row.values
            if value.strip() not in _EMPTY_VALUES
            for line in name_lines(value, stacked=self._document.stacked_names)
        ]
        line_count = 2 if self._document.stacked_names else 1

        def measure(text: str, size: float) -> float:
            return self._metrics(_font(size, bold=True)).horizontalAdvance(text)

        def fits_height(size: float) -> bool:
            line_height = self._metrics(_font(size, bold=True)).height()
            return line_height * line_count <= row_height - 2 * self._padding

        return fit_font_size(
            texts, room=self._workday_room(), measure=measure, fits_height=fits_height
        )

    def draw(self, painter: QPainter) -> None:
        pages = self.pages()
        smallest_row = min((self._row_height(len(page)) for page in pages if page), default=0)
        value_size = self._value_font_size(smallest_row) if smallest_row else _MAX_FONT_PT
        for page_index, rows in enumerate(pages):
            if page_index:
                self._writer.newPage()
            self._draw_title(painter)
            table_top = _millimeters(_TITLE_HEIGHT_MM)
            self._draw_header(painter, table_top)
            row_height = self._row_height(len(rows))
            body_top = table_top + _millimeters(_HEADER_HEIGHT_MM)
            for offset, row_index in enumerate(rows):
                self._draw_row(
                    painter,
                    self._document.rows[row_index],
                    body_top + offset * row_height,
                    row_height,
                    value_size,
                )
            table_bottom = body_top + len(rows) * row_height
            self._draw_grid(painter, table_top, table_bottom, len(rows), row_height)
            self._draw_footer(painter, table_bottom, page_index, len(pages))

    def _draw_text(
        self,
        painter: QPainter,
        rect: QRectF,
        text: str,
        font: QFont,
        color: QColor,
    ) -> None:
        """Disegna ``text`` centrato nel rettangolo; se non entra lo comprime in larghezza."""

        available = rect.width() - 2 * self._padding
        needed = self._metrics(font).horizontalAdvance(text)
        painter.save()
        painter.setFont(font)
        painter.setPen(color)
        if needed > available > 0:
            center = rect.center().x()
            painter.translate(center, 0)
            painter.scale(available / needed, 1)
            painter.translate(-center, 0)
            rect = QRectF(center - needed / 2, rect.top(), needed, rect.height())
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def _draw_title(self, painter: QPainter) -> None:
        left_center = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        painter.save()
        painter.setPen(_TEXT_COLOR)
        painter.setFont(_font(14, bold=True))
        painter.drawText(
            QRectF(0, 0, self._width, _millimeters(7)), left_center, self._document.title
        )
        painter.setPen(_MUTED_COLOR)
        painter.setFont(_font(8))
        painter.drawText(
            QRectF(0, _millimeters(7), self._width, _millimeters(5)),
            left_center,
            self._document.period,
        )
        painter.restore()

    def _draw_header(self, painter: QPainter, top: float) -> None:
        height = _millimeters(_HEADER_HEIGHT_MM)
        label_rect = QRectF(0, top, self._label_width, height)
        painter.fillRect(label_rect, _HEADER_BACKGROUND)
        self._draw_text(painter, label_rect, "Attività", _font(8, bold=True), _TEXT_COLOR)
        left = self._label_width
        for index, header in enumerate(self._document.column_headers):
            width = self._column_widths[index]
            rest = index in self._document.rest_columns
            background = _REST_DAY_BACKGROUND if rest else _HEADER_BACKGROUND
            painter.fillRect(QRectF(left, top, width, height), background)
            number, _, day = header.partition(" ")
            self._draw_text(
                painter,
                QRectF(left, top, width, height / 2),
                number,
                _font(6.5 if rest else 8, bold=True),
                _MUTED_COLOR if rest else _TEXT_COLOR,
            )
            if day:
                self._draw_text(
                    painter,
                    QRectF(left, top + height / 2, width, height / 2),
                    day[:1] if rest else day,
                    _font(6 if rest else 7),
                    _MUTED_COLOR if rest else _LABEL_TEXT_COLOR,
                )
            left += width

    def _draw_row(
        self, painter: QPainter, row: CalendarPdfRow, top: float, height: float, size: float
    ) -> None:
        label_rect = QRectF(0, top, self._label_width, height)
        painter.fillRect(label_rect, QColor(row.background))
        painter.save()
        painter.setPen(_LABEL_TEXT_COLOR)
        painter.setFont(_font(8, bold=True))
        painter.drawText(
            label_rect.adjusted(2 * self._padding, 0, -self._padding, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
            row.label,
        )
        painter.restore()

        cell_background = _tint(row.background)
        left = self._label_width
        for index, value in enumerate(row.values):
            width = self._column_widths[index]
            rect = QRectF(left, top, width, height)
            left += width
            if index in self._document.rest_columns:
                painter.fillRect(rect, _REST_DAY_BACKGROUND)
                continue
            painter.fillRect(rect, cell_background)
            text = value.strip()
            if text in _EMPTY_VALUES:
                continue
            color = row.value_colors.get(text)
            if color:
                self._draw_text(painter, rect, text, _font(size + 1, bold=True), QColor(color))
                continue
            lines = name_lines(text, stacked=self._document.stacked_names)
            line_height = self._metrics(_font(size, bold=True)).height()
            first_top = rect.center().y() - line_height * len(lines) / 2
            for number, line in enumerate(lines):
                self._draw_text(
                    painter,
                    QRectF(rect.left(), first_top + number * line_height, width, line_height),
                    line,
                    _font(size, bold=number == 0),
                    _TEXT_COLOR,
                )

    def _draw_grid(
        self, painter: QPainter, top: float, bottom: float, rows: int, row_height: float
    ) -> None:
        painter.save()
        pen = QPen(_GRID_COLOR)
        pen.setWidthF(1)
        painter.setPen(pen)
        header_bottom = top + _millimeters(_HEADER_HEIGHT_MM)
        row_lines = (header_bottom + k * row_height for k in range(1, rows + 1))
        for y in (top, header_bottom, *row_lines):
            painter.drawLine(QPointF(0, y), QPointF(self._width, y))
        x = 0.0
        painter.drawLine(QPointF(x, top), QPointF(x, bottom))
        for width in (self._label_width, *self._column_widths):
            x += width
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))
        painter.restore()

    def _draw_footer(
        self, painter: QPainter, table_bottom: float, page_index: int, page_count: int
    ) -> None:
        top = table_bottom + _millimeters(_FOOTER_GAP_MM)
        rect = QRectF(0, top, self._width, self._height - top)
        painter.save()
        painter.setFont(_font(7))
        painter.setPen(_MUTED_COLOR)
        painter.drawText(
            QRectF(rect.left(), rect.top(), self._width * 0.85, rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            "\n".join(self._footer_lines()),
        )
        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            f"Pagina {page_index + 1} di {page_count}",
        )
        painter.restore()


def write_calendar_pdf(path: str | Path, document: CalendarPdfDocument) -> Path:
    """Crea il PDF su A4 orizzontale e restituisce il percorso del file.

    Raises:
        CalendarPdfError: se il file non può essere creato o scritto.
    """

    output_path = Path(path)
    if output_path.suffix.casefold() != ".pdf":
        output_path = output_path.with_suffix(".pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    writer = QPdfWriter(str(output_path))
    writer.setResolution(_RESOLUTION_DPI)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Landscape)
    writer.setPageMargins(
        QMarginsF(_MARGIN_MM, _MARGIN_MM, _MARGIN_MM, _MARGIN_MM), QPageLayout.Unit.Millimeter
    )
    writer.setTitle(document.title)
    writer.setCreator("MMSD CV")

    painter = QPainter(writer)
    if not painter.isActive():
        raise CalendarPdfError(f"Impossibile creare il PDF in {output_path}")
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # L'origine del painter è già dentro i margini della pagina e ogni colore è
        # esplicito: il risultato non dipende dal tema del desktop.
        _Renderer(writer, document).draw(painter)
    finally:
        painter.end()

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise CalendarPdfError(f"Il PDF non è stato scritto in {output_path}")
    return output_path
