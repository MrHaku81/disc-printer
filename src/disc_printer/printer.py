from .i18n import _


class DiscPrinter:
    def __init__(self, name: str, ppd_path: str,
                 input_slot: str | None,
                 media_type: str | None,
                 media_size: str,
                 temporary: bool = False):
        self.name       = name
        self.ppd_path   = ppd_path
        self.input_slot = input_slot
        self.media_type = media_type
        self.media_size = media_size
        # Treiberloses Ziel ohne dauerhafte Queue (nur in `lpstat -e`);
        # CUPS legt die Warteschlange erst beim Drucken temporär an.
        self.temporary  = temporary

    @property
    def lp_options(self) -> list[str]:
        opts: list[str] = []
        if self.input_slot:
            opts += ["-o", f"InputSlot={self.input_slot}"]
        if self.media_type:
            opts += ["-o", f"MediaType={self.media_type}"]
        opts += ["-o", f"media={self.media_size}"]
        opts += ["-o", "print-quality=5", "-o", "ColorModel=RGB"]
        return opts

    @property
    def lp_command_str(self) -> str:
        return f"lp -d {self.name} {' '.join(self.lp_options)} <datei>"


def lp_error_message(printer: DiscPrinter, lp_error: str) -> str:
    """
    Text für die GUI, wenn `lp` fehlschlägt.

    Feste Queues: die lp-Meldung wie bisher.  Temporäre (treiberlose) Ziele:
    eine verständliche Erklärung statt z. B. "lp: No such file or directory"
    — CUPS 2.4.20 kann temporäre Queues wegen eines Fehlers in cupsd nicht
    anlegen (OpenPrinting/cups#1751, behoben im Zweig 2.4.x).
    """
    if not printer.temporary:
        return _("Druckfehler:\n%s") % lp_error
    # TRANSLATORS: Shown when printing to a driverless printer without a
    # permanent CUPS queue fails. "CUPS 2.4.20" is a version number.
    return _(
        "Der treiberlose Drucker konnte nicht angesprochen werden: CUPS hat "
        "keine temporäre Warteschlange angelegt.\n\n"
        "Bei CUPS 2.4.20 ist das ein bekannter Fehler. Abhilfe: den Drucker "
        "in den Druckereinstellungen fest einrichten."
    )
