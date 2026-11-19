"""Tests für das Zusammenführen von `lpstat -p` und `lpstat -e` (Issue #2).

Kein echtes CUPS: subprocess.run wird in disc_printer.detection gemockt.
"""
import subprocess
import unittest
from unittest import mock

from disc_printer import detection as det

P_OUT = (
    "printer Canon_TS705a is idle.  enabled since Mon Nov  9 15:32:51 2026\n"
    "printer RICOH+M+C240FW is idle.  enabled since Wed Nov 11 21:10:16 2026\n"
)
E_OUT_LONG = (
    "Canon_TS705a permanent ipp://localhost/printers/Canon_TS705a "
    "ipp://E1F4F9000000.local:631/ipp/print\n"
    "Canon_TS700_series network none dnssd://Canon%20TS700%20series._ipps."
    "_tcp.local/?uuid=00000000-0000-1000-8000-00186d156ee9\n"
    "RICOH+M+C240FW permanent ipp://localhost/printers/RICOH+M+C240FW "
    "ipp://ET788C77D664E8.local:631/ipp/print\n"
)
CANON_DNSSD = ("dnssd://Canon%20TS700%20series._ipps._tcp.local/"
               "?uuid=00000000-0000-1000-8000-00186d156ee9")


def _cp(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def _fake_lpstat(p=None, e=None):
    """p/e: CompletedProcess oder Exception für `lpstat -p` bzw. `lpstat -l -e`."""
    def run(cmd, **kw):
        assert cmd[0] == "lpstat", cmd
        res = e if "-e" in cmd else p
        if isinstance(res, BaseException):
            raise res
        return res if res is not None else _cp()
    return run


class ParseTests(unittest.TestCase):
    def test_parse_p(self):
        self.assertEqual(det._parse_lpstat_p(P_OUT),
                         ["Canon_TS705a", "RICOH+M+C240FW"])

    def test_parse_p_empty(self):
        self.assertEqual(det._parse_lpstat_p(""), [])

    def test_parse_e_short(self):
        self.assertEqual(det._parse_lpstat_e("A\nB\n\n"),
                         [("A", None), ("B", None)])

    def test_parse_e_long_uri(self):
        res = dict(det._parse_lpstat_e(E_OUT_LONG))
        self.assertEqual(res["Canon_TS700_series"], CANON_DNSSD)
        self.assertEqual(res["Canon_TS705a"],
                         "ipp://E1F4F9000000.local:631/ipp/print")

    def test_parse_e_instances_and_duplicates(self):
        out = "Canon/disc\nCanon\nCanon/photo\nOther/x\nOther/y\n"
        self.assertEqual(det._parse_lpstat_e(out),
                         [("Canon", None), ("Other", None)])

    def test_parse_e_device_uri_none(self):
        self.assertEqual(det._parse_lpstat_e("X network none none\n"),
                         [("X", None)])


class MergeTests(unittest.TestCase):
    def test_union_without_duplicates_p_first(self):
        dests = det._merge_destinations(
            ["A", "B"], [("B", None), ("C", "dnssd://c"), ("A", None)])
        self.assertEqual([d.name for d in dests], ["A", "B", "C"])
        self.assertEqual([d.temporary for d in dests], [False, False, True])
        self.assertEqual(dests[2].device_uri, "dnssd://c")
        self.assertIsNone(dests[0].device_uri)

    def test_both_empty(self):
        self.assertEqual(det._merge_destinations([], []), [])

    def test_only_e(self):
        dests = det._merge_destinations([], [("T", None)])
        self.assertEqual(dests, [det._Dest("T", True, None)])


class LpstatDestinationsTests(unittest.TestCase):
    def _run(self, **kw):
        with mock.patch.object(det.subprocess, "run",
                               side_effect=_fake_lpstat(**kw)):
            return det._lpstat_destinations()

    def test_merge_real_world(self):
        dests = self._run(p=_cp(P_OUT), e=_cp(E_OUT_LONG))
        self.assertEqual([d.name for d in dests],
                         ["Canon_TS705a", "RICOH+M+C240FW", "Canon_TS700_series"])
        self.assertEqual([d.name for d in dests if d.temporary],
                         ["Canon_TS700_series"])
        self.assertEqual(dests[2].device_uri, CANON_DNSSD)

    def test_empty_outputs(self):
        self.assertEqual(self._run(p=_cp(""), e=_cp("")), [])

    def test_e_unsupported_nonzero_rc(self):
        dests = self._run(p=_cp(P_OUT),
                          e=_cp("", 1, 'lpstat: Unknown option "e".'))
        self.assertEqual([d.name for d in dests],
                         ["Canon_TS705a", "RICOH+M+C240FW"])
        self.assertFalse(any(d.temporary for d in dests))

    def test_e_timeout(self):
        dests = self._run(p=_cp(P_OUT),
                          e=subprocess.TimeoutExpired("lpstat", 6))
        self.assertEqual(len(dests), 2)

    def test_e_oserror(self):
        dests = self._run(p=_cp(P_OUT), e=OSError("boom"))
        self.assertEqual(len(dests), 2)

    def test_lpstat_missing(self):
        self.assertEqual(
            self._run(p=FileNotFoundError(), e=FileNotFoundError()), [])

    def test_p_fails_e_works(self):
        dests = self._run(p=FileNotFoundError(), e=_cp("A\nA/inst\n"))
        self.assertEqual(dests, [det._Dest("A", True, None)])

    def test_lpstat_names_wrapper(self):
        with mock.patch.object(det.subprocess, "run", side_effect=_fake_lpstat(
                p=_cp(P_OUT), e=_cp("Canon_TS705a/disc\nNew\n"))):
            self.assertEqual(det._lpstat_names(),
                             ["Canon_TS705a", "RICOH+M+C240FW", "New"])


class IppFallbackTests(unittest.TestCase):
    IPPTOOL_OUT = (
        "    Get printer attributes using get-printer-attributes   [PASS]\n"
        "        media-supported (1setOf keyword) = iso_a4_210x297mm,"
        "om_square_120x120mm,custom_min_55x89mm\n"
        "        media-type-supported (1setOf keyword) = stationery,"
        "photographic,envelope,disc\n"
        "        media-source-supported (1setOf keyword) = auto,main,rear,disc\n"
    )

    def setUp(self):
        det._ipp_cache.clear()
        w = mock.patch.object(det.shutil, "which", return_value="/usr/bin/x")
        w.start()
        self.addCleanup(w.stop)

    def test_ppdize(self):
        self.assertEqual(det._ppdize("disc"), "Disc")
        self.assertEqual(det._ppdize("photographic-glossy"),
                         "PhotographicGlossy")

    def test_cmd_dnssd(self):
        cmd = det._ipptool_cmd(CANON_DNSSD)
        self.assertEqual(cmd[:4], ["ippfind", "-T", "3", "_ipps._tcp"])
        self.assertIn("^Canon TS700 series$", cmd)
        self.assertLess(cmd.index("-p"), cmd.index("-x"))
        self.assertEqual(cmd[-1], ";")

    def test_cmd_ipp_and_unsupported(self):
        self.assertEqual(det._ipptool_cmd("ipp://h:631/ipp/print")[-2],
                         "ipp://h:631/ipp/print")
        self.assertIsNone(det._ipptool_cmd("usb://Canon/TS700"))

    def test_query_disc(self):
        with mock.patch.object(det.subprocess, "run",
                               return_value=_cp(self.IPPTOOL_OUT)):
            self.assertEqual(det._query_via_ipp(CANON_DNSSD),
                             ("Disc", "Disc", "om_square_120x120mm"))

    def test_query_no_disc(self):
        out = ("        media-source-supported (1setOf keyword) = auto,tray-1\n"
               "        media-type-supported (1setOf keyword) = stationery\n")
        with mock.patch.object(det.subprocess, "run", return_value=_cp(out)):
            self.assertIsNone(det._query_via_ipp(CANON_DNSSD))

    def test_query_tool_missing(self):
        with mock.patch.object(det.subprocess, "run",
                               side_effect=FileNotFoundError()):
            self.assertIsNone(det._query_via_ipp(CANON_DNSSD))

    def test_detect_caps_ipp_only_with_device_uri(self):
        with mock.patch.object(det, "_find_ppd", return_value=None), \
             mock.patch.object(det, "_query_via_lpoptions", return_value=None), \
             mock.patch.object(det, "_query_via_cups_http", return_value=None), \
             mock.patch.object(det, "_query_via_ipp",
                               return_value=("Disc", "Disc", "x")) as ipp:
            self.assertEqual(det._detect_caps("Q"), (None, "cups-http"))
            ipp.assert_not_called()
            self.assertEqual(det._detect_caps("T", CANON_DNSSD),
                             (("Disc", "Disc", "x"), "ipp"))


class IppToolsMissingTests(unittest.TestCase):
    def setUp(self):
        det._ipp_cache.clear()
        det._ipp_tools_warned = False
        self.addCleanup(setattr, det, "_ipp_tools_warned", False)

    def test_warns_once_and_names_package(self):
        with mock.patch.object(det.shutil, "which", return_value=None), \
             mock.patch.object(det.subprocess, "run") as run, \
             self.assertLogs("disc_printer", "WARNING") as cm:
            self.assertIsNone(det._query_via_ipp(CANON_DNSSD))
            self.assertIsNone(det._query_via_ipp("ipp://other:631/ipp/print"))
            run.assert_not_called()
        self.assertEqual(len(cm.output), 1)
        self.assertIn("ipptool and ippfind", cm.output[0])
        self.assertIn("cups-ipp-utils", cm.output[0])

    def test_only_ippfind_missing(self):
        which = lambda t: None if t == "ippfind" else "/usr/bin/" + t
        with mock.patch.object(det.shutil, "which", side_effect=which), \
             self.assertLogs("disc_printer", "WARNING") as cm:
            self.assertIsNone(det._query_via_ipp(CANON_DNSSD))
        self.assertIn("ippfind not found", cm.output[0])

    def test_ipp_uri_needs_only_ipptool(self):
        which = lambda t: None if t == "ippfind" else "/usr/bin/" + t
        with mock.patch.object(det.shutil, "which", side_effect=which), \
             mock.patch.object(det.subprocess, "run",
                               return_value=_cp("")) as run:
            det._query_via_ipp("ipp://h:631/ipp/print")
            run.assert_called_once()


RICOH_DNSSD = ("dnssd://M%20C240FW._ipps._tcp.local/"
               "?uuid=85bc217b-8b9e-4ee1-9f97-8a0c69cb5dea")


class DuplicateDeviceTests(unittest.TestCase):
    def setUp(self):
        det._ipp_cache.clear()

    def test_device_keys(self):
        k = det._device_keys
        self.assertEqual(k("ipp://E1F4F9000000.local:631/ipp/print"),
                         {("host", "e1f4f9000000.local")})
        self.assertEqual(k("ipps://ET788C77D664E8.local.:443/ipp/print"),
                         {("host", "et788c77d664e8.local")})
        self.assertEqual(k("socket://192.168.1.5:9100"),
                         {("host", "192.168.1.5")})
        self.assertEqual(k(CANON_DNSSD), {("dnssd", "canon ts700 series")})
        self.assertEqual(k("ipp://localhost/printers/X"), set())
        self.assertEqual(k("file:/dev/null"), set())
        self.assertEqual(k("usb://Canon/TS700?serial=1"), set())
        self.assertEqual(k(None), set())

    def test_resolved_uri_from_ippfind_output(self):
        out = ("\"/usr/share/cups/ipptool/get-printer-attributes.test\":\n"
               "        printer-uri-supported (1setOf uri) = "
               "ipp://ET788C77D664E8.local:631/ipp/print\n"
               "ipps://ET788C77D664E8.local:443/ipp/print\n")
        with mock.patch.object(det.shutil, "which", return_value="/x"), \
             mock.patch.object(det.subprocess, "run", return_value=_cp(out)):
            info = det._ipp_lookup(RICOH_DNSSD)
        self.assertEqual(info.resolved_uri,
                         "ipps://ET788C77D664E8.local:443/ipp/print")

    def test_lookup_is_cached(self):
        with mock.patch.object(det.shutil, "which", return_value="/x"), \
             mock.patch.object(det.subprocess, "run",
                               return_value=_cp("")) as run:
            det._ipp_lookup(RICOH_DNSSD)
            det._ipp_lookup(RICOH_DNSSD)
            run.assert_called_once()

    def test_twin_by_resolved_host(self):
        perm = {("host", "et788c77d664e8.local"): "RICOH+M+C240FW"}
        dest = det._Dest("M_C240FW", True, RICOH_DNSSD)
        self.assertEqual(det._find_permanent_twin(
            dest, perm, "ipps://ET788C77D664E8.local:443/ipp/print"),
            "RICOH+M+C240FW")

    def test_twin_by_dnssd_name(self):
        perm = {("dnssd", "canon ts700 series"): "Canon_Perm"}
        dest = det._Dest("Canon_TS700_series", True, CANON_DNSSD)
        self.assertEqual(det._find_permanent_twin(dest, perm), "Canon_Perm")

    def test_no_twin_other_host(self):
        perm = {("host", "other.local"): "Other"}
        dest = det._Dest("M_C240FW", True, RICOH_DNSSD)
        self.assertIsNone(det._find_permanent_twin(
            dest, perm, "ipps://ET788C77D664E8.local:443/ipp/print"))

    def test_no_comparison_possible_keeps_dest(self):
        perm = {("host", "et788c77d664e8.local"): "RICOH+M+C240FW"}
        self.assertIsNone(det._find_permanent_twin(
            det._Dest("M_C240FW", True, RICOH_DNSSD), perm, None))
        self.assertIsNone(det._find_permanent_twin(
            det._Dest("M_C240FW", True, None), perm, None))
        self.assertIsNone(det._find_permanent_twin(
            det._Dest("M_C240FW", True, RICOH_DNSSD), {},
            "ipps://ET788C77D664E8.local:443/ipp/print"))

    def test_merge_keeps_permanent_device_uri(self):
        dests = det._merge_destinations(
            ["Canon_TS705a"], det._parse_lpstat_e(E_OUT_LONG))
        self.assertEqual(dests[0].device_uri,
                         "ipp://E1F4F9000000.local:631/ipp/print")
        self.assertFalse(dests[0].temporary)

    def test_detect_hides_twin_and_logs(self):
        dests = [
            det._Dest("Canon_TS705a", False,
                      "ipp://E1F4F9000000.local:631/ipp/print"),
            det._Dest("Canon_TS700_series", True, CANON_DNSSD),
            det._Dest("Lonely", True, "dnssd://Lonely._ipp._tcp.local/"),
        ]
        services = {
            ("_ipps._tcp", "canon ts700 series"):
                "ipps://E1F4F9000000.local:631/ipp/print",
            ("_ipp._tcp", "lonely"): "ipp://lonely.local:631/ipp/print",
        }
        caps = (("Disc", "Disc", "120x120mm"), "x")
        with mock.patch.object(det, "_lpstat_destinations", return_value=dests), \
             mock.patch.object(det, "_browse_ipp_services",
                               return_value=services) as browse, \
             mock.patch.object(det, "_ipp_lookup") as lookup, \
             mock.patch.object(det, "_detect_caps", return_value=caps) as dc, \
             self.assertLogs("disc_printer", "INFO") as cm:
            found = det.detect_disc_printers()
        browse.assert_called_once()
        # ipptool nur für das übrig gebliebene Ziel, mit aufgelöster URI
        lookup.assert_called_once_with("dnssd://Lonely._ipp._tcp.local/",
                                       "ipp://lonely.local:631/ipp/print")
        self.assertEqual([p.name for p in found], ["Canon_TS705a", "Lonely"])
        self.assertEqual([p.temporary for p in found], [False, True])
        self.assertTrue(any("Canon_TS700_series: hidden" in l
                            and "'Canon_TS705a'" in l for l in cm.output))
        self.assertFalse(any("Checking 'Canon_TS700_series'" in l
                             for l in cm.output))
        self.assertEqual(dc.call_args_list[0].args, ("Canon_TS705a", None))
        self.assertEqual(dc.call_args_list[1].args,
                         ("Lonely", "dnssd://Lonely._ipp._tcp.local/"))

    def test_detect_browse_failed_keeps_temp(self):
        dests = [
            det._Dest("Canon_TS705a", False,
                      "ipp://E1F4F9000000.local:631/ipp/print"),
            det._Dest("Canon_TS700_series", True, CANON_DNSSD),
        ]
        with mock.patch.object(det, "_lpstat_destinations", return_value=dests), \
             mock.patch.object(det, "_browse_ipp_services", return_value=None), \
             mock.patch.object(det, "_ipp_lookup") as lookup, \
             mock.patch.object(det, "_detect_caps",
                               return_value=(("Disc", "Disc", "m"), "x")):
            found = det.detect_disc_printers()
        self.assertEqual([p.name for p in found],
                         ["Canon_TS705a", "Canon_TS700_series"])
        # Fallback wie bisher: Abfrage ohne aufgelöste URI (ippfind je Ziel)
        lookup.assert_called_once_with(CANON_DNSSD, None)


class BrowseTests(unittest.TestCase):
    def setUp(self):
        det._ipp_cache.clear()
        w = mock.patch.object(det.shutil, "which", return_value="/usr/bin/x")
        w.start()
        self.addCleanup(w.stop)

    OUT = ("Canon TS700 series\tipp://E1F4F9000000.local:631/ipp/print\n"
           "M C240FW\tipp://ET788C77D664E8.local:631/ipp/print\n"
           "Canon TS700 series\tipps://E1F4F9000000.local:631/ipp/print\n"
           "M C240FW\tipps://ET788C77D664E8.local:443/ipp/print\n"
           "garbage line\n")

    def test_browse_parses_name_and_uri(self):
        with mock.patch.object(det.subprocess, "run",
                               return_value=_cp(self.OUT)) as run:
            svc = det._browse_ipp_services()
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[:5], ["ippfind", "-T", "3", "_ipp._tcp", "_ipps._tcp"])
        self.assertEqual(svc[("_ipps._tcp", "m c240fw")],
                         "ipps://ET788C77D664E8.local:443/ipp/print")
        self.assertEqual(svc[("_ipp._tcp", "canon ts700 series")],
                         "ipp://E1F4F9000000.local:631/ipp/print")
        self.assertEqual(len(svc), 4)

    def test_browse_failure_returns_none(self):
        with mock.patch.object(det.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("x", 1)):
            self.assertIsNone(det._browse_ipp_services())

    def test_browse_tools_missing(self):
        det._ipp_tools_warned = True
        self.addCleanup(setattr, det, "_ipp_tools_warned", False)
        with mock.patch.object(det.shutil, "which", return_value=None), \
             mock.patch.object(det.subprocess, "run") as run:
            self.assertIsNone(det._browse_ipp_services())
            run.assert_not_called()

    def test_resolve_temporary(self):
        dests = [det._Dest("A", True, RICOH_DNSSD),
                 det._Dest("B", True, "ipp://b.local:631/ipp/print"),
                 det._Dest("C", True, "dnssd://Unknown._ipp._tcp.local/"),
                 det._Dest("D", True, None)]
        with mock.patch.object(det, "_browse_ipp_services", return_value={
                ("_ipps._tcp", "m c240fw"): "ipps://ET.local:443/ipp/print"}):
            res = det._resolve_temporary(dests)
        self.assertEqual(res, {
            RICOH_DNSSD: "ipps://ET.local:443/ipp/print",
            "ipp://b.local:631/ipp/print": "ipp://b.local:631/ipp/print",
        })

    def test_resolve_without_dnssd_skips_browse(self):
        with mock.patch.object(det, "_browse_ipp_services") as browse:
            det._resolve_temporary([det._Dest("B", True, "ipp://b/x")])
            browse.assert_not_called()

    def test_lookup_with_resolved_uses_ipptool_directly(self):
        with mock.patch.object(det.subprocess, "run",
                               return_value=_cp("")) as run:
            info = det._ipp_lookup(RICOH_DNSSD, "ipps://ET.local:443/ipp/print")
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[0], "ipptool")
        self.assertIn("ipps://ET.local:443/ipp/print", cmd)
        self.assertEqual(info.resolved_uri, "ipps://ET.local:443/ipp/print")
        self.assertIn(RICOH_DNSSD, det._ipp_cache)

    def test_prefetch_runs_in_parallel(self):
        import threading, time as _t
        active, peak, lock = [0], [0], threading.Lock()

        def slow(uri, resolved=None):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            _t.sleep(0.05)
            with lock:
                active[0] -= 1

        dests = [det._Dest(f"T{i}", True, f"ipp://h{i}/x") for i in range(4)]
        with mock.patch.object(det, "_ipp_lookup", side_effect=slow) as lk:
            det._prefetch_ipp(dests, {})
        self.assertEqual(lk.call_count, 4)
        self.assertGreater(peak[0], 1)


if __name__ == "__main__":
    unittest.main()
