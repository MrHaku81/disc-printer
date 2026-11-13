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
