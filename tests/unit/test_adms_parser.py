"""Tests for ADMS/iClock protocol parser."""

import pytest

from bip.connectors.zk_adms.parser import (
    parse_attlog,
    parse_command_results,
    parse_operlog,
    render_commands,
    render_handshake,
    strip_templates,
)


@pytest.mark.unit
class TestParseAttlog:
    def test_single_punch(self):
        body = "10001\t2026-10-21 08:30:00\t0\t1\t\t0\t0"
        punches = parse_attlog(body)
        assert len(punches) == 1
        assert punches[0].device_pin == "10001"
        assert punches[0].verify_mode == "fingerprint"
        assert punches[0].io_state == "in"

    def test_multiple_punches(self):
        body = (
            "10001\t2026-10-21 08:30:00\t0\t1\t\t0\t0\n"
            "10002\t2026-10-21 08:31:00\t1\t9\t\t0\t0\n"
            "10003\t2026-10-21 08:32:00\t0\t4\t\t0\t0"
        )
        punches = parse_attlog(body)
        assert len(punches) == 3
        assert punches[1].verify_mode == "face"
        assert punches[1].io_state == "out"
        assert punches[2].verify_mode == "card"
        assert punches[2].io_state == "in"

    def test_empty_body(self):
        assert parse_attlog("") == []
        assert parse_attlog("\n\n") == []

    def test_malformed_line_skipped(self):
        body = "bad line\n10001\t2026-10-21 08:30:00\t0\t1\t\t0\t0"
        punches = parse_attlog(body)
        assert len(punches) == 1

    def test_workcode_captured(self):
        body = "10001\t2026-10-21 08:30:00\t0\t1\tWC01\t0\t0"
        punches = parse_attlog(body)
        assert punches[0].work_code == "WC01"

    def test_thousand_punches(self):
        lines = [
            f"1000{i % 100:02d}\t2026-10-{21 + i // 1440:02d} {(8 + i // 60) % 24:02d}:{i % 60:02d}:00\t0\t1\t\t0\t0"
            for i in range(1000)
        ]
        body = "\n".join(lines)
        punches = parse_attlog(body)
        assert len(punches) == 1000


@pytest.mark.unit
class TestParseOperlog:
    def test_user_record(self):
        body = "USER PIN=10001\tName=John Doe\tPri=0\tCard=1234\tGrp=1"
        result = parse_operlog(body)
        assert len(result.users) == 1
        assert result.users[0].pin == "10001"
        assert result.users[0].card_no == "1234"

    def test_fp_record(self):
        body = "FP PIN=10001\tFID=0\tTMP=base64data"
        result = parse_operlog(body)
        assert "10001" in result.enrolment_counts
        assert result.enrolment_counts["10001"]["fingerprints"] == 1

    def test_mixed_records(self):
        body = (
            "USER PIN=10001\tName=A\tPri=0\n"
            "FP PIN=10001\tFID=0\tTMP=data\n"
            "FP PIN=10001\tFID=1\tTMP=data\n"
            "USER PIN=10002\tName=B\tPri=0"
        )
        result = parse_operlog(body)
        assert len(result.users) == 2
        assert result.enrolment_counts["10001"]["fingerprints"] == 2


@pytest.mark.unit
class TestStripTemplates:
    def test_strips_tmp_field(self):
        body = "FP PIN=10001\tFID=0\tTMP=longbase64datahere"
        result = strip_templates(body)
        assert "longbase64datahere" not in result
        assert "TMP=" in result

    def test_preserves_non_template_fields(self):
        body = "USER PIN=10001\tName=John\tCard=1234"
        result = strip_templates(body)
        assert "John" not in result or "Name" in result
        assert "1234" in result


@pytest.mark.unit
class TestCommandResults:
    def test_parse_success(self):
        body = "ID=1&Return=0&CMD=DATA UPDATE USERINFO"
        results = parse_command_results(body)
        assert len(results) == 1
        assert results[0].cmd_no == 1
        assert results[0].success is True

    def test_parse_failure(self):
        body = "ID=2&Return=-1&CMD=DATA DELETE USERINFO"
        results = parse_command_results(body)
        assert len(results) == 1
        assert results[0].success is False
        assert results[0].return_code == -1

    def test_multiple_results(self):
        body = "ID=1&Return=0&CMD=A\nID=2&Return=0&CMD=B"
        results = parse_command_results(body)
        assert len(results) == 2


@pytest.mark.unit
class TestRenderHandshake:
    def test_default_handshake(self):
        result = render_handshake("ABC123")
        assert "GET OPTION FROM: ABC123" in result
        assert "TransFlag=TransData AttLog OpLog EnrollUser ChgUser" in result
        assert "ATTPHOTOStamp=None" in result
        assert "Encrypt=None" in result

    def test_custom_stamp(self):
        result = render_handshake("X", attlog_stamp="2026-10-21 00:00:00")
        assert "ATTLOGStamp=2026-10-21 00:00:00" in result


@pytest.mark.unit
class TestRenderCommands:
    def test_single_command(self):
        result = render_commands([(1, "DATA UPDATE USERINFO PIN=10001\tName=Test")])
        assert result == "C:1:DATA UPDATE USERINFO PIN=10001\tName=Test"

    def test_multiple_commands(self):
        cmds = [(1, "CMD1"), (2, "CMD2")]
        result = render_commands(cmds)
        assert "C:1:CMD1" in result
        assert "C:2:CMD2" in result
