#!/usr/bin/env python
"""
Offline tests: histories saved in tests/data/histories and fake students made from them,
each with one known difference to the reference.
"""

import copy
import json

import ghevaluator

from pathlib import Path

DATA = Path(__file__).parent / "data" / "histories"
REF_ID = "c1ad4cd9d7df4ada"  # GTN From Peaks to Genes, reference
STUDENT_ID = "892319be4e2b6ca2"  # GTN From Peaks to Genes, another run
TB_ID = "92de4a3edad93e3e"  # collections and mapped over steps


def load(hist_id):
    with (DATA / f"{hist_id}.json").open() as f:
        return ghevaluator.build_workflow(json.load(f))


def compare(hist_wf, ref_wf, fetch_text=None):
    return ghevaluator.compare_workflows(hist_wf, ref_wf, {"inputs": {}}, fetch_text=fetch_text)


def step_by_tool(wf, key, occurrence=0):
    return [k for k, s in wf["steps"].items() if s["tool_id"] and ghevaluator.tool_key(s["tool_id"]) == key][occurrence]


def set_parameter(step, name, value):
    state = json.loads(step["tool_state"])
    state[name] = value
    step["tool_state"] = json.dumps(state)


def test_build_workflow_resolves_all_connections():
    for hist_id in [REF_ID, STUDENT_ID, TB_ID]:
        wf = load(hist_id)
        for step in wf["steps"].values():
            assert all(step["input_connections"].values()), (hist_id, step["name"])


def test_group_summary_jobs_merges_mapped_over_entries():
    """In copied histories, a mapped over step can be listed once per collection element"""
    jobs = [
        {"id": "a", "step_type": "tool", "implicit_collection_jobs_id": "icj", "outputs": [{"id": "d1"}]},
        {"id": "a", "step_type": "tool", "implicit_collection_jobs_id": "icj", "outputs": [{"id": "d2"}]},
        {"id": "b", "step_type": "tool", "implicit_collection_jobs_id": None, "outputs": [{"id": "d3"}]},
        {"id": "c", "step_type": "tool", "invalid": "fake_job", "outputs": []},
    ]
    steps = ghevaluator.history.group_summary_jobs(jobs)
    assert [s["id"] for s in steps] == ["a", "b"]
    assert [o["id"] for o in steps[0]["outputs"]] == ["d1", "d2"]


def test_normalize_parameters():
    assert ghevaluator.clean_parameters('{"a": "\\"7\\"", "b": 7, "c": "null", "d": {"__class__": "ConnectedValue"}, "chromInfo": "x", "__use_cached_job__": "true"}') == {
        "a": "7", "b": "7", "c": None}


def test_data_inputs_and_element_names_are_not_settings():
    """Datasets picked in a job, connected inputs in a workflow file and collection element names are not settings"""
    job = {
        "reference_source": {"__current_case__": 1, "fasta_ref": {"values": [{"id": 157186850, "src": "hda"}]}, "reference_source_selector": "history"},
        "input_file|__identifier__": "ERR1203059",
        "queries": [{"input2": {"values": [{"id": 1, "src": "hda"}]}, "header": "true"}],
    }
    workflow = {"reference_source": {"fasta_ref": {"__class__": "ConnectedValue"}, "reference_source_selector": "history"}, "queries": [{"input2": {"__class__": "ConnectedValue"}, "header": True}]}
    assert ghevaluator.clean_parameters(job) == ghevaluator.clean_parameters(workflow) == {
        "reference_source": {"reference_source_selector": "history"}, "queries": [{"header": "true"}]}


def test_multiple_inputs_are_not_settings():
    """Numbered inputs of a multiple input (inputs1 ... inputs20) are not settings"""
    tb = load(TB_ID)
    cat = tb["steps"][step_by_tool(tb, "tp_cat")]
    assert len(cat["input_connections"]) > 20
    assert list(ghevaluator.clean_parameters(cat["tool_state"])) == ["queries"]


def test_same_history():
    ref = load(REF_ID)
    report = compare(copy.deepcopy(ref), ref)
    assert report["score"]["steps"] == 100.0
    assert report["score"]["missing_steps"] == 0
    assert report["score"]["extra_steps"] == 0
    assert report["score"]["copied_steps"] == 0
    assert all(c["inputs_connection"]["same"] for c in report["comparison_given_reference_workflow_order"].values())


def test_other_tool_version():
    ref = load(REF_ID)
    hist = copy.deepcopy(ref)
    k = step_by_tool(hist, "get_flanks1")
    hist["steps"][k]["tool_id"] = hist["steps"][k]["tool_id"].replace("1.0.0", "1.0.1")
    report = compare(hist, ref)
    changed = [c for c in report["comparison_given_reference_workflow_order"].values() if not c["version"]["same"]]
    assert [c["id"]["workflow"] for c in changed] == ["get_flanks1"]
    assert report["score"]["steps"] == 100.0  # a newer tool version is reported, not penalized


def test_wrong_parameter():
    ref = load(REF_ID)
    hist = copy.deepcopy(ref)
    k = step_by_tool(hist, "Grouping1")
    set_parameter(hist["steps"][k], "ignorecase", "true")
    report = compare(hist, ref)
    step = next(c for c in report["comparison_given_reference_workflow_order"].values() if c["order"]["workflow"] == k)
    assert step["parameters"]["wrong"] == 1
    assert not step["parameters"]["details"]["ignorecase"]["same"]
    assert report["score"]["steps"] < 100.0


def test_missing_last_step():
    ref = load(REF_ID)
    hist = copy.deepcopy(ref)
    del hist["steps"]["9"]  # last Sort
    del hist["steps"]["10"]  # a Sort the tutor deleted, a deleted run still counts as done
    report = compare(hist, ref)
    assert report["score"]["missing_steps"] == 1
    assert report["comparison_given_reference_workflow_order"][7]["status"] == "missing"


def test_thrown_away_reference_step_is_not_asked():
    """A step the tutor deleted and did not use is not asked from the students"""
    ref = load(REF_ID)
    assert ref["steps"]["10"]["deleted"]
    hist = copy.deepcopy(ref)
    del hist["steps"]["10"]
    report = compare(hist, ref)
    assert report["score"]["steps"] == 100.0
    assert report["score"]["missing_steps"] == 0
    assert report["steps"]["workflow"] == 8
    # a deleted output still used by a later step is a real step
    k = step_by_tool(ref, "Grouping1")
    for o in ref["steps"][k]["outputs"]:
        o["deleted"] = True
    ref["steps"][k]["deleted"] = True
    assert int(k) not in ghevaluator.match.thrown_away(ref["steps"])


def test_failed_step_is_not_done():
    ref = load(REF_ID)
    hist = copy.deepcopy(ref)
    k = step_by_tool(hist, "Grouping1")
    hist["steps"][k]["failed"] = True
    report = compare(hist, ref)
    group = next(c for c in report["comparison_given_reference_workflow_order"].values() if c["id"]["workflow"] == "Grouping1")
    assert group["status"] == "missing"
    assert report["score"]["failed_steps"] == 1
    assert report["score"]["extra_steps"] == 0
    assert "Failed or not finished, so not counted as done: Group." in report["in_short"]
    # a failed attempt of the tutor is not asked either
    report = compare(copy.deepcopy(hist), hist)
    assert report["score"]["missing_steps"] == 0
    assert report["steps"]["workflow"] == 7


def test_kept_run_is_preferred_to_deleted_run():
    """Right settings in a deleted run, wrong settings in the kept and used run: the kept run counts"""
    ref = load(REF_ID)
    hist = copy.deepcopy(ref)
    k = step_by_tool(hist, "Grouping1")
    deleted = copy.deepcopy(hist["steps"][k])
    deleted["id"] = len(hist["steps"])
    deleted["deleted"] = True
    hist["steps"][str(deleted["id"])] = deleted
    set_parameter(hist["steps"][k], "ignorecase", "true")
    report = compare(hist, ref)
    group = next(c for c in report["comparison_given_reference_workflow_order"].values() if c["id"]["workflow"] == "Grouping1")
    assert group["order"]["history"] == k
    assert group["parameters"]["wrong"] == 1
    assert [s["order"] for s in report["extra_steps"]] == [str(deleted["id"])]


def test_missing_middle_step_breaks_connections():
    ref = load(REF_ID)
    hist = copy.deepcopy(ref)
    k = step_by_tool(hist, "CONVERTER_interval_to_bed_0")
    before = ghevaluator.connection_ids(hist["steps"][k])[0]
    del hist["steps"][k]
    # the intersect step now gets its input from the step before the removed one
    i = step_by_tool(hist, "gops_intersect_1")
    for c in hist["steps"][i]["input_connections"].values():
        if c["id"] == int(k):
            c["id"] = before
    report = compare(hist, ref)
    by_tool = {c["id"]["workflow"]: c for c in report["comparison_given_reference_workflow_order"].values()}
    assert by_tool["CONVERTER_interval_to_bed_0"]["status"] == "missing"
    assert by_tool["gops_intersect_1"]["status"] == "matched"
    assert not by_tool["gops_intersect_1"]["inputs_connection"]["same"]


def test_rerun_step_is_extra():
    """A step run twice: the run used by the next steps is matched, the other is extra"""
    ref = load(REF_ID)
    hist = copy.deepcopy(ref)
    k = step_by_tool(hist, "Grouping1")
    rerun = copy.deepcopy(hist["steps"][k])
    rerun["id"] = len(hist["steps"])
    rerun["end_time"] = "2099-01-01T00:00:00"
    set_parameter(rerun, "ignorecase", "true")
    hist["steps"][str(rerun["id"])] = rerun
    report = compare(hist, ref)
    assert report["score"]["steps"] == 100.0
    assert [s["order"] for s in report["extra_steps"]] == [str(rerun["id"])]


def test_other_order():
    """Independent steps run in another order are still matched"""
    ref = load(REF_ID)
    hist = copy.deepcopy(ref)
    # get flanks (5) only depends on an input, move it to the end
    moved = hist["steps"].pop("5")
    new_index = len(ref["steps"])
    moved["id"] = new_index
    hist["steps"][str(new_index)] = moved
    for step in hist["steps"].values():
        for c in step["input_connections"].values():
            if c.get("id") == 5:
                c["id"] = new_index
    report = compare(hist, ref)
    assert report["score"]["steps"] == 100.0
    assert report["score"]["missing_steps"] == 0
    assert report["score"]["extra_steps"] == 0


def test_copied_and_cached_steps():
    ref = load(REF_ID)
    hist = copy.deepcopy(ref)
    k = step_by_tool(hist, "Grouping1")
    hist["steps"][k]["history_id"] = "someone_else"
    j = step_by_tool(hist, "get_flanks1")
    hist["steps"][j]["cached"] = True
    report = compare(hist, ref)
    assert report["score"]["copied_steps"] == 1
    assert report["copied_steps"][0]["history"] == "someone_else"
    assert report["score"]["cached_steps"] == 1
    flags = {c["id"]["workflow"]: c for c in report["comparison_given_reference_workflow_order"].values()}
    assert flags["Grouping1"]["copied_from_history"] == "someone_else"
    assert flags["get_flanks1"]["cached"]
    assert not flags["get_flanks1"]["cached_reference"]
    self_flags = {c["id"]["workflow"]: c for c in compare(hist, hist)["comparison_given_reference_workflow_order"].values()}
    assert self_flags["get_flanks1"]["cached"] and self_flags["get_flanks1"]["cached_reference"]


def test_imported_copy_is_not_flagged_as_copied():
    """A history imported by a tutor has all jobs in the original history: nothing is copied"""
    ref = load(REF_ID)
    hist = copy.deepcopy(ref)
    hist["history_id"] = "tutor_copy"
    hist["main_history_id"] = ghevaluator.history.get_main_history_id("tutor_copy", hist["steps"])
    assert hist["main_history_id"] == REF_ID
    report = compare(hist, ref)
    assert report["score"]["copied_steps"] == 0
    # but it is said, a student could also share a copy of someone else's whole history
    assert report["score"]["all_steps_from_history"] == REF_ID
    report["inputs"] = {"history": "h", "workflow": "w"}
    assert f"All steps of this history ran in history {REF_ID}" in ghevaluator.generate_markdown_report_content(report)
    assert compare(load(REF_ID), ref)["score"]["all_steps_from_history"] is None


def test_inaccessible_job():
    """A job that can not be read (e.g. copied from a private history) does not stop the evaluation"""
    with (DATA / f"{STUDENT_ID}.json").open() as f:
        history = json.load(f)
    job = next(j for j in history["summary"]["jobs"] if j["step_type"] == "tool" and "gops_intersect" in j["tool_id"])
    del history["jobs"][job["id"]]
    hist = ghevaluator.build_workflow(history)
    step = next(s for s in hist["steps"].values() if s.get("job_id") == job["id"])
    assert step["inaccessible"]
    report = compare(hist, load(REF_ID))
    assert report["score"]["copied_steps"] == 1
    assert report["copied_steps"][0]["history"] == "not accessible"
    intersect = next(c for c in report["comparison_given_reference_workflow_order"].values() if c["id"]["workflow"] == "gops_intersect_1")
    assert intersect["status"] == "matched"
    assert intersect["copied_from_history"] == "not accessible"


def test_real_other_run():
    """Another run of the same tutorial: the final sort steps were not done, some steps were run again"""
    ref = load(REF_ID)
    hist = load(STUDENT_ID)
    report = compare(hist, ref)
    missing = [c["id"]["workflow"] for c in report["comparison_given_reference_workflow_order"].values() if c["status"] == "missing"]
    assert missing == ["tp_sort_header_tool"]
    # 4 steps not in the reference, 3 of them deleted by the student
    assert len(report["extra_steps"]) == 4
    assert report["score"]["extra_steps"] == 1
    assert report["score"]["deleted_steps"] == 3
    matched = [c for c in report["comparison_given_reference_workflow_order"].values() if c["status"] == "matched"]
    assert all(c["inputs_connection"]["same"] for c in matched)
    assert report["final_outputs"]["tool_found"] is False


def test_final_output_content():
    ref = load(REF_ID)
    hist = copy.deepcopy(ref)
    texts = {"ref": "a\t1\nb\t2\nc\t3\n", "same": "a\t1\nb\t2\nc\t3\n", "other": "a\t1\nb\t9\nc\t3\n"}
    # the last step of the reference which was not deleted
    last = max((s for s in ref["steps"].values() if s["type"] == "tool" and not s["deleted"]), key=lambda s: s["end_time"])
    # make the history outputs different datasets from the reference outputs
    for step in hist["steps"].values():
        for o in step["outputs"]:
            o["id"] = "h" + o["id"]

    case = {"history": "same"}

    def fetch_by_id(galaxy_url, dataset_id):
        return texts["ref"] if not dataset_id.startswith("h") else texts[case["history"]]

    report = compare(hist, ref, fetch_by_id)
    assert report["final_outputs"]["reference_step"]["order"] == str(last["id"])
    assert report["score"]["final_output"] == 100.0
    case["history"] = "other"
    report = compare(hist, ref, fetch_by_id)
    assert 0 < report["score"]["final_output"] < 100.0


def test_collections_and_mapped_steps():
    tb = load(TB_ID)
    report = compare(copy.deepcopy(tb), tb)
    assert report["score"]["steps"] == 100.0
    assert report["data_inputs"]["workflow"] == 3


def test_reports_render():
    ref = load(REF_ID)
    report = compare(load(STUDENT_ID), ref)
    report["inputs"] = {"history": "h", "workflow": "w", "reference": "w", "reference_type": "history"}
    html = ghevaluator.generate_html_report_content(report)
    assert "Steps not in the reference" in html and "Final output" in html
    md = ghevaluator.generate_markdown_report_content(report)
    assert "| Step score | 87.5 % |" in md
    assert "missing" in md


def test_read_students_csv(tmp_path):
    csv_fp = tmp_path / "students.csv"
    csv_fp.write_text(
        "Tutorial name,Ref hist id,Stud hist id,Student name\n"
        "peaks,c1ad4cd9d7df4ada,https://usegalaxy.eu/histories/view?id=892319be4e2b6ca2,Student A\n"
        ",,,\n")
    rows = ghevaluator.read_students_csv(csv_fp, "https://usegalaxy.eu")
    assert rows == [{
        "student": "Student A",
        "tutorial": "peaks",
        "history": "https://usegalaxy.eu/histories/view?id=892319be4e2b6ca2",
        "reference": "https://usegalaxy.eu/histories/view?id=c1ad4cd9d7df4ada",
    }]
    assert ghevaluator.safe_name("Student A / B") == "Student_A_B"


def test_in_short():
    report = compare(load(STUDENT_ID), load(REF_ID))
    assert report["in_short"] == ["7 of 8 steps done. Missing: Sort.", "Extra steps: Select last."]
    ref = load(REF_ID)
    hist = copy.deepcopy(ref)
    set_parameter(hist["steps"][step_by_tool(hist, "Grouping1")], "ignorecase", "true")
    assert compare(hist, ref)["in_short"] == ["All 8 steps done.", "Different settings (number of parameters): Group (1)."]


def test_overview():
    report = compare(load(STUDENT_ID), load(REF_ID))
    rows = [
        {"student": "Student A", "tutorial": "peaks", "report": "Student_A_peaks/report.md", "score": report["score"], "in_short": report["in_short"], "error": None},
        {"student": "Student B", "tutorial": "peaks", "report": "Student_B_peaks/report.md", "score": None, "in_short": [], "error": "400 Client Error"},
    ]
    content = ghevaluator.generate_overview_content(rows)
    assert "| Student A | peaks | 87.5 % |  | 7 of 8 steps done. Missing: Sort. Extra steps: Select last. | [report](Student_A_peaks/report.md) |" in content
    assert "Could not be evaluated: 400 Client Error" in content


def test_slug_link_needs_api_key():
    assert ghevaluator.history.find_history_by_slug("https://usegalaxy.eu", "/u/someone/h/some-history") is None
    assert ghevaluator.history.find_history_by_slug("https://usegalaxy.eu", "/histories/list", "key") is None


def test_self_comparison_is_exact():
    """A history compared to itself matches every step with itself"""
    for path in sorted(DATA.glob("*.json")):
        wf = load(path.stem)
        mapping = ghevaluator.match_steps(wf["steps"], wf["steps"])["mapping"]
        assert all(r == h for r, h in mapping.items()), path.stem
        assert compare(copy.deepcopy(wf), wf)["score"]["steps"] == 100.0, path.stem


def test_identical_runs_are_matched_in_order():
    """Runs with the same tool, inputs and settings: the 1st matches the 1st, the 2nd the 2nd"""
    ref = load(REF_ID)
    k = step_by_tool(ref, "Grouping1")
    twin = copy.deepcopy(ref["steps"][k])
    twin["id"] = len(ref["steps"])
    ref["steps"][str(twin["id"])] = twin
    hist = copy.deepcopy(ref)
    mapping = ghevaluator.match_steps(ref["steps"], hist["steps"])["mapping"]
    assert mapping[int(k)] == int(k)
    assert mapping[twin["id"]] == twin["id"]


def test_swapped_inputs_are_not_the_same():
    """Intersect A with B is not intersect B with A"""
    ref = load(REF_ID)
    hist = copy.deepcopy(ref)
    k = step_by_tool(hist, "gops_intersect_1")
    connections = hist["steps"][k]["input_connections"]
    (n1, c1), (n2, c2) = list(connections.items())
    assert c1["id"] != c2["id"]
    connections[n1], connections[n2] = c2, c1
    report = compare(hist, ref)
    intersect = next(c for c in report["comparison_given_reference_workflow_order"].values() if c["id"]["workflow"] == "gops_intersect_1")
    assert not intersect["inputs_connection"]["same"]
    assert report["score"]["steps"] < 100.0


def test_multiple_input_names_are_merged():
    step = {"input_connections": {"inputs": {"id": 1}, "inputs1": {"id": 2}, "input1": {"id": 3}, "input2": [{"id": 4}]}}
    assert ghevaluator.match.connections_by_name(step) == {"inputs": [1, 2], "input1": [3], "input2": [4]}


def test_workflow_file_reference_has_no_output_formats():
    """Outputs of a workflow file (.ga) have no format to compare and no final output"""
    ref = load(REF_ID)
    ga = {"steps": copy.deepcopy(ref["steps"])}
    for step in ga["steps"].values():
        step["outputs"] = [{"name": "out_file1", "type": "tabular"}]
    report = compare(load(STUDENT_ID), ga)
    assert not any("output_formats" in c for c in report["comparison_given_reference_workflow_order"].values())
    assert "final_outputs" not in report
    assert not any(s.startswith("Other output formats") for s in report["in_short"])


def test_job_cache_row_only_for_done_steps():
    ref = load(REF_ID)
    k = step_by_tool(ref, "Grouping1")
    ref["steps"][k]["cached"] = True
    hist = copy.deepcopy(ref)
    report = compare(hist, ref)
    report["inputs"] = {"history": "h", "workflow": "w"}
    assert "job cache (also in the reference)." in ghevaluator.generate_markdown_report_content(report)
    del hist["steps"][k]
    report = compare(hist, ref)
    report["inputs"] = {"history": "h", "workflow": "w"}
    assert "Result reused from an earlier job" not in ghevaluator.generate_html_report_content(report)


def test_api_key_only_sent_to_its_server():
    """A link given by a student must not get the tutor's API key"""
    ghevaluator.check_key_host("https://usegalaxy.eu/histories/view?id=1", "key", "https://usegalaxy.eu")
    ghevaluator.check_key_host("https://attacker.example/histories/view?id=1", None, "https://usegalaxy.eu")
    for url in ("https://attacker.example/histories/view?id=1", "http://usegalaxy.eu/histories/view?id=1"):
        try:
            ghevaluator.evaluate(url, "https://usegalaxy.eu/histories/view?id=2", "key", ref_wf=({}, "history"))
        except ValueError as e:
            assert "only sent to the Galaxy server" in str(e)
        else:
            raise AssertionError(url)


def test_reference_type_is_not_guessed_when_given(monkeypatch):
    calls = []
    monkeypatch.setattr(ghevaluator, "api_get", lambda url, path, key=None, params=None: calls.append((url, path)) or {"steps": {}})
    monkeypatch.setattr(ghevaluator, "get_workflow_from_history", lambda url, key=None: calls.append(("history", url)) or {"steps": {}})
    assert ghevaluator.get_reference("https://usegalaxy.eu/published/workflow?id=abc", ref_type="workflow")[1] == "workflow"
    assert calls[-1] == ("https://usegalaxy.eu", "workflows/abc/download")
    assert ghevaluator.get_reference("https://usegalaxy.eu/published/workflow?id=abc")[1] == "workflow"
    assert ghevaluator.get_reference("https://usegalaxy.eu/u/a/workflows/b", ref_type="history")[1] == "history"
