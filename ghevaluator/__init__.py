#!/usr/bin/env python3

import csv
import json
import re
import requests

from jinja2 import Environment, PackageLoader, select_autoescape
from pathlib import Path
from urllib import parse

from ghevaluator.history import (  # noqa: F401
    build_workflow,
    fetch_dataset_text,
    get_hist_info,
    get_workflow_from_history,
    load_history,
)
from ghevaluator.match import (  # noqa: F401
    clean_parameters,
    connection_ids,
    is_input_step,
    match_steps,
    same_connections,
    text_similarity,
    tool_key,
)


def get_standard_workflow(wf_url):
    """
    Turn the workflow in a provided link into a dictionary, as the standard to be compared with the user workflow.

    :param wf_url: link to the standard workflow file
    :return: dictionary with the workflow
    """
    r = requests.get(wf_url)
    return r.json()


def is_input(step):
    """
    Check if a step is an input step

    :param step: dictionary with a workflow step
    :return: boolean
    """
    return is_input_step(step)


def count_wf_inputs(wf):
    """
    Count the numbers of the inputs in a workflow

    :param wf: a workflow
    :return: number of inputs in the workflow
    """
    return sum(1 for step in wf.values() if is_input(step))


def get_input_id(unkw_dict):
    """
    Recursive function looking for the id number inside the part of the dictionary of the input connections.

    :param unkw_dict: unknown layers of length of input connections as a sub dictionary
    :return: a list of integers representing the input id numbers
    """
    ids = []
    for key, item in unkw_dict.items():
        if isinstance(item, list):
            ids.extend(get_input_id(dict(enumerate(item))))
        elif isinstance(item, dict) and 'id' in item:
            ids.append(item['id'])
        else:
            ids.append(-1)
    return ids


def split_id(tool_id):
    """
    Split the long tool id extracted from workflow into ToolShed owner, short tool id name, tool version

    :param tool_id: "content_id" from workflow file

    :return: owner, tool id, tool version
    """
    split_tool_id = str(tool_id).split("/")
    if len(split_tool_id) >= 6:
        owner = split_tool_id[2]
        id = split_tool_id[4]
        version = split_tool_id[5]
    else:
        owner = None
        id = None
        version = None
    return owner, id, version


def reformate_workflows(wf):
    """
    Reformate workflow steps into a list and a dictionary with key being the tool names

    :param wf: workflow steps
    :return: list and dictionary
    """
    ordered_wf = []
    wf_by_tools = {}
    for key, step in wf.items():
        if is_input(step):
            continue
        tool = step['name']
        owner, id, version = split_id(step['tool_id'])
        step_dict = {
            "tool": tool,
            "id": id if id is not None else step['tool_id'],
            "owner": owner,
            "version": version if version is not None else step.get('tool_version'),
            "parameters": clean_parameters(step['tool_state']),
            "inputs_connection": get_input_id(step['input_connections']),
            "order": key
        }
        ordered_wf.append(step_dict)
        wf_by_tools.setdefault(tool, [])
        wf_by_tools[tool].append(step_dict)
    return ordered_wf, wf_by_tools


def fill_step_comparison(ref_step, hist_step, key):
    """
    Compare reference and history steps for a specific key

    :param ref_step: dictionary with reference step
    :param hist_step: dictionary with history step
    :param key: key of values to compare
    :return: dictionary with workflow, history, same
    """
    hist_value = hist_step[key] if hist_step is not None else None
    return {
        'workflow': ref_step[key],
        'history': hist_value,
        'same': bool(ref_step[key] == hist_value)
    }


def fill_step_report(ref_step, hist_step=None):
    """
    Prepare the report for a step

    :param ref_step: dictionary with reference step
    :param hist_step: dictionary with history step
    :return: dictionary
    """
    s_report = {
        "tool": fill_step_comparison(ref_step, hist_step, 'tool'),
        "id": fill_step_comparison(ref_step, hist_step, 'id'),
        "owner": fill_step_comparison(ref_step, hist_step, 'owner'),
        "version": fill_step_comparison(ref_step, hist_step, 'version'),
        "order": fill_step_comparison(ref_step, hist_step, 'order'),
        "parameters": {
            'number': {
                'workflow': len(ref_step['parameters']),
                'history': len(hist_step['parameters']) if hist_step is not None else None,
                'same': bool(len(ref_step['parameters']) == len(hist_step['parameters'])) if hist_step is not None else False
            },
            'wrong': len(ref_step['parameters']),
            'details': {}
        },
        "inputs_connection": fill_step_comparison(ref_step, hist_step, 'inputs_connection')
    }
    # compare parameters
    for p in ref_step['parameters']:
        s_report['parameters']['details'][p] = {
            'workflow': ref_step['parameters'][p],
            'history': hist_step['parameters'][p] if hist_step is not None and p in hist_step['parameters'] else None,
            'same': bool(ref_step['parameters'][p] == hist_step['parameters'][p]) if hist_step is not None and p in hist_step['parameters'] else False
        }
        if s_report['parameters']['details'][p]['same']:
            s_report['parameters']['wrong'] -= 1
    return s_report


def compare_ordered_steps(ref_steps, hist_steps):
    """
    Compare ordered steps, the step at the same position in both lists must use the same tool

    Kept for compatibility, `compare_workflows` matches steps with `match_steps`.

    :param ref_steps: list of steps in reference workflow
    :param hist_steps: list of steps in history workflow
    :return: dictionary with comparison
    """
    comparison = {}
    h_step_count = 0
    for i, ref_step in enumerate(ref_steps):
        if hist_steps is not None and h_step_count < len(hist_steps) and ref_step['tool'] == hist_steps[h_step_count]['tool']:
            comparison[i] = fill_step_report(ref_step, hist_steps[h_step_count])
            h_step_count += 1
        else:
            comparison[i] = fill_step_report(ref_step, None)
    return comparison


def output_formats(step):
    """
    Get the formats of the outputs of a step from a history

    :param step: workflow step built from a history
    :return: sorted list of formats (collections as "collection")
    """
    return sorted((o.get("extension") or "?") if o["type"] == "dataset" else "collection" for o in step.get("outputs", []))


def step_score(step_report):
    """
    Score of a reference step: 0 if missing, 0.5 if the tool is found,
    up to 0.25 more for connections and 0.25 for parameters

    :param step_report: comparison of the step
    :return: number between 0 and 1
    """
    if step_report['status'] == 'missing':
        return 0.0
    nb_params = step_report['parameters']['number']['workflow']
    params = 1.0 if nb_params == 0 else 1 - step_report['parameters']['wrong'] / nb_params
    return 0.5 + 0.25 * step_report['inputs_connection']['same'] + 0.25 * params


def compare_final_outputs(ref_wf, hist_wf, fetch_text=None, nb_last=5):
    """
    Compare the output of the last step of a reference history to the outputs of the last steps of a history

    Steps are ordered by the end time of their job. Content is compared for the first dataset output,
    if `fetch_text` is given and the datasets are text.

    :param ref_wf: workflow built from the reference history
    :param hist_wf: workflow built from the history
    :param fetch_text: function (galaxy_url, dataset_id) -> text or None
    :param nb_last: number of last history steps to compare
    :return: dictionary with the comparison, None if the reference has no job end time
    """
    ref_tools = [s for s in ref_wf['steps'].values() if s['type'] == 'tool' and s.get('end_time')]
    if not ref_tools:
        return None
    ref_last = max(ref_tools, key=lambda s: s['end_time'])
    hist_last = sorted(
        (s for s in hist_wf['steps'].values() if s['type'] == 'tool' and s.get('end_time')),
        key=lambda s: s['end_time'], reverse=True)[:nb_last]

    def first_dataset_text(wf, step):
        datasets = [o for o in step.get('outputs', []) if o['type'] == 'dataset']
        if fetch_text is None or not datasets:
            return None
        return fetch_text(wf['galaxy_url'], datasets[0]['id'])

    ref_text = first_dataset_text(ref_wf, ref_last)
    candidates = []
    for step in hist_last:
        text = first_dataset_text(hist_wf, step) if ref_text is not None else None
        candidates.append({
            'order': str(step['id']),
            'tool': step['name'],
            'same_tool': tool_key(step['tool_id']) == tool_key(ref_last['tool_id']),
            'outputs': {'workflow': len(ref_last['outputs']), 'history': len(step['outputs']), 'same': len(ref_last['outputs']) == len(step['outputs'])},
            'formats': {'workflow': output_formats(ref_last), 'history': output_formats(step), 'same': output_formats(ref_last) == output_formats(step)},
            'content_similarity': round(text_similarity(ref_text, text), 3) if text is not None else None,
        })
    similarities = [c['content_similarity'] for c in candidates if c['content_similarity'] is not None]
    return {
        'reference_step': {'order': str(ref_last['id']), 'tool': ref_last['name'], 'formats': output_formats(ref_last)},
        'candidates': candidates,
        'best_content_similarity': max(similarities) if similarities else None,
        'tool_found': any(c['same_tool'] for c in candidates),
    }


def compare_workflows(hist_wf, ref_wf, report, fetch_text=None):
    """
    Compare a history workflow to a reference workflow and generate a report

    The reference can be a workflow file or a workflow built from a reference history.
    With a reference history, output formats and the final outputs are compared too.

    :param hist_wf: dictionary with workflow built from the history
    :param ref_wf: dictionary with reference workflow
    :param report: dictionary to fill
    :param fetch_text: optional function (galaxy_url, dataset_id) -> text, to compare final output content
    :return: dictionary with report
    """
    hist_steps = hist_wf['steps']
    ref_steps = ref_wf['steps']
    ordered_hist_wf, hist_wf_by_tool = reformate_workflows(hist_steps)
    ordered_ref_wf, ref_wf_by_tool = reformate_workflows(ref_steps)
    report['reference_wf'] = ordered_ref_wf
    report['history_wf'] = ordered_hist_wf
    # Compare inputs in both workflows
    hist_wf_input_nb = count_wf_inputs(hist_steps)
    ref_wf_input_nb = count_wf_inputs(ref_steps)
    report['data_inputs'] = {
        "workflow": ref_wf_input_nb,
        "history": hist_wf_input_nb,
        "same": bool(ref_wf_input_nb == hist_wf_input_nb)
    }
    # Compare number of steps in both workflows
    hist_step_nb = len(hist_steps) - hist_wf_input_nb
    ref_step_nb = len(ref_steps) - ref_wf_input_nb
    report['steps'] = {
        'workflow': ref_step_nb,
        'history': hist_step_nb,
        'same': bool(ref_step_nb == hist_step_nb)
    }
    # Match steps and compare matched steps
    matching = match_steps(ref_steps, hist_steps)
    mapping = matching['mapping']
    hist_by_order = {s['order']: s for s in ordered_hist_wf}
    main_history = hist_wf.get('main_history_id')
    comparison = {}
    for i, ref_step in enumerate(ordered_ref_wf):
        raw_ref = ref_steps[ref_step['order']]
        h = mapping.get(int(ref_step['order']))
        raw_hist = hist_steps[str(h)] if h is not None else None
        s_report = fill_step_report(ref_step, hist_by_order[str(h)] if h is not None else None)
        s_report['status'] = 'matched' if h is not None else 'missing'
        s_report['inputs_connection'] = {
            'workflow': connection_ids(raw_ref),
            'history': connection_ids(raw_hist) if raw_hist else None,
            'same': bool(raw_hist and same_connections(raw_ref, raw_hist, mapping)),
        }
        s_report['cached'] = bool(raw_hist and raw_hist.get('cached'))
        copied_from = raw_hist.get('history_id') if raw_hist else None
        s_report['copied_from_history'] = copied_from if copied_from and main_history and copied_from != main_history else None
        if raw_hist and 'outputs' in raw_ref:
            s_report['output_formats'] = {
                'workflow': output_formats(raw_ref),
                'history': output_formats(raw_hist),
                'same': output_formats(raw_ref) == output_formats(raw_hist),
            }
        comparison[i] = s_report
    report['comparison_given_reference_workflow_order'] = comparison
    # Compare workflows by tools
    by_tool = {}
    for tool, ref_tool_steps in ref_wf_by_tool.items():
        details = {}
        for j, ref_step in enumerate(ref_tool_steps):
            details[j] = next(c for i, c in comparison.items() if ordered_ref_wf[i] is ref_step)
        by_tool[tool] = {
            'number': {
                'workflow': len(ref_tool_steps),
                'history': len(hist_wf_by_tool.get(tool, [])),
                'same': len(ref_tool_steps) == len(hist_wf_by_tool.get(tool, []))
            },
            'details': details
        }
    report['comparison_by_reference_workflow_tools'] = by_tool
    # Steps of the history not in the reference
    report['extra_steps'] = [{
        'order': str(h),
        'tool': hist_steps[str(h)]['name'],
        'id': hist_by_order[str(h)]['id'],
        'version': hist_by_order[str(h)]['version'],
        'cached': bool(hist_steps[str(h)].get('cached')),
    } for h in matching['extra']]
    # Steps whose job ran in another history, i.e. results copied from someone else
    report['copied_steps'] = [{
        'order': k,
        'tool': s['name'],
        'history': s['history_id'],
    } for k, s in hist_steps.items() if s.get('history_id') and main_history and s['history_id'] != main_history]
    if 'outputs' in next(iter(ref_steps.values()), {}):
        report['final_outputs'] = compare_final_outputs(ref_wf, hist_wf, fetch_text)
    scores = [step_score(c) for c in comparison.values()]
    final = report.get('final_outputs') or {}
    report['score'] = {
        'steps': round(100 * sum(scores) / len(scores), 1) if scores else None,
        'final_output': round(100 * final['best_content_similarity'], 1) if final.get('best_content_similarity') is not None else None,
        'missing_steps': len(matching['missing']),
        'extra_steps': len(matching['extra']),
        'copied_steps': len(report['copied_steps']),
        'cached_steps': sum(1 for s in hist_steps.values() if s.get('cached')),
    }
    return report


def get_template_env():
    """
    Get the Jinja environment with the report templates
    """
    return Environment(
        loader=PackageLoader("ghevaluator", "templates"),
        autoescape=select_autoescape(enabled_extensions=("html",))
    )


def generate_html_report_content(data):
    """
    Generate HTML report

    :param data: dictionary holding the information of the status of key features of user history
    """
    return get_template_env().get_template("report.html").render(report=data)


def generate_markdown_report_content(data):
    """
    Generate Markdown report

    :param data: dictionary holding the information of the status of key features of user history
    """
    return get_template_env().get_template("report.md").render(report=data)


def generate_report_files(data, output_dp):
    """
    Convert the report dictionary into a JSON file, a HTML file and a Markdown file

    :param data: dictionary holding the information of the status of key features of user history
    :param output_dp: Path object of the output directory
    """
    output_dp.mkdir(parents=True, exist_ok=True)

    json_fp = output_dp / Path("report.json")
    with json_fp.open('w') as out_f:
        json.dump(data, out_f, ensure_ascii=False, indent=4)

    html_fp = output_dp / Path("report.html")
    with html_fp.open('w') as out_f:
        out_f.write(generate_html_report_content(data))

    md_fp = output_dp / Path("report.md")
    with md_fp.open('w') as out_f:
        out_f.write(generate_markdown_report_content(data))


def is_workflow_url(url):
    """
    Check if a URL points to a workflow file rather than to a history

    :param url: URL
    :return: boolean
    """
    path = parse.urlparse(url).path
    return path.endswith(".ga") or "/workflows/" in path


def get_reference(ref_url, apikey=None):
    """
    Get the reference workflow from a workflow file URL or a history URL

    :param ref_url: URL to a workflow file (.ga) or to a Galaxy history
    :param apikey: optional API key for a history
    :return: workflow dictionary and reference type ('workflow' or 'history')
    """
    if is_workflow_url(ref_url):
        return get_standard_workflow(ref_url), 'workflow'
    return get_workflow_from_history(ref_url, apikey), 'history'


def evaluate(hist_url, ref_url, apikey=None, ref_wf=None):
    """
    Compare a history to a reference and return the report

    :param hist_url: URL to Galaxy history
    :param ref_url: URL to reference workflow file or reference history
    :param apikey: optional Galaxy API key
    :param ref_wf: optional reference already loaded with `get_reference`, as (workflow, type)
    :return: dictionary with report
    """
    ref, ref_type = ref_wf if ref_wf is not None else get_reference(ref_url, apikey)
    hist_wf = get_workflow_from_history(hist_url, apikey)
    report = {'inputs': {'history': hist_url, 'workflow': ref_url, 'reference': ref_url, 'reference_type': ref_type}}
    return compare_workflows(hist_wf, ref, report, fetch_text=lambda url, ds: fetch_dataset_text(url, ds, apikey))


def ghevaluator(hist_url, wf_url, apikey, output_dp):
    """
    The main function: compare a history to a reference and write the report files

    :param hist_url: URL to Galaxy history
    :param wf_url: URL to reference workflow file or reference history
    :param apikey: a Galaxy API key, optional for published or shared histories
    :param output_dp: Path object of the output report
    """
    generate_report_files(evaluate(hist_url, wf_url, apikey), output_dp)


def read_students_csv(csv_fp, galaxy_url):
    """
    Read the list of histories to evaluate

    Columns (case insensitive): student name (or student), stud hist id (or student_history),
    ref hist id (or ref_history) and an optional tutorial name. History columns can be history ids
    or URLs, the reference can also be a URL to a workflow file.

    :param csv_fp: path to the CSV file
    :param galaxy_url: Galaxy URL used for history ids
    :return: list of dictionaries with student, tutorial, history and reference URLs
    """
    def to_url(value):
        value = value.strip()
        return value if value.startswith("http") else f"{galaxy_url.rstrip('/')}/histories/view?id={value}"

    rows = []
    with open(csv_fp, newline='') as f:
        for row in csv.DictReader(f):
            row = {(k or '').strip().lower(): (v or '').strip() for k, v in row.items()}
            student = row.get('student name') or row.get('student')
            hist = row.get('stud hist id') or row.get('student_history')
            ref = row.get('ref hist id') or row.get('ref_history')
            if not (student and hist and ref):
                continue
            rows.append({'student': student, 'tutorial': row.get('tutorial name', ''), 'history': to_url(hist), 'reference': to_url(ref)})
    return rows


def safe_name(name):
    """
    Turn a name into a folder name

    :param name: any name
    :return: name with only letters, digits, - and _
    """
    return re.sub(r'[^\w-]+', '_', name, flags=re.UNICODE).strip('_') or 'history'


def ghevaluator_batch(csv_fp, output_dp, apikey=None, galaxy_url="https://usegalaxy.eu"):
    """
    Evaluate several histories listed in a CSV file and write one report per history and an overview

    :param csv_fp: path to the CSV file, see `read_students_csv`
    :param output_dp: Path object of the output directory
    :param apikey: optional Galaxy API key
    :param galaxy_url: Galaxy URL used for history ids in the CSV file
    :return: list of overview rows
    """
    references = {}
    overview = []
    for row in read_students_csv(csv_fp, galaxy_url):
        folder = safe_name(row['student'])
        entry = dict(row, report=f"{folder}/report.md", score=None, error=None)
        try:
            if row['reference'] not in references:
                references[row['reference']] = get_reference(row['reference'], apikey)
            report = evaluate(row['history'], row['reference'], apikey, references[row['reference']])
            generate_report_files(report, output_dp / folder)
            entry['score'] = report['score']
        except Exception as e:  # keep going with the other histories
            entry['error'] = str(e)
        overview.append(entry)
    output_dp.mkdir(parents=True, exist_ok=True)
    with (output_dp / "overview.json").open('w') as out_f:
        json.dump(overview, out_f, ensure_ascii=False, indent=4)
    with (output_dp / "overview.md").open('w') as out_f:
        out_f.write(get_template_env().get_template("overview.md").render(rows=overview))
    return overview
