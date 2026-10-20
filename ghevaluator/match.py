"""
Match the steps of a history to the steps of a reference (workflow or history)

Steps are matched by tool and by where their inputs come from, not by their order,
so reruns, extra steps and steps run in another order are handled.
"""

import json
from difflib import SequenceMatcher

INPUT_TYPES = ("data_input", "data_collection_input", "parameter_input")

# parameters depending on the Galaxy server or the run, not on the analysis
IGNORED_PARAMETERS = ["__page__", "__input_ext", "chromInfo", "__rerun_remap_job_id__", "dbkey", "__job_resource", "__workflow_invocation_uuid__", "__use_cached_job__"]


def is_input_step(step):
    """
    Check if a workflow step is an input step

    :param step: dictionary with a workflow step
    :return: boolean
    """
    return step["name"] in ("Input dataset", "Data Fetch") or step["type"] in INPUT_TYPES


def tool_key(tool_id):
    """
    Get the part of a tool id that does not depend on the tool version or ToolShed

    :param tool_id: full tool id, e.g. toolshed.g2.bx.psu.edu/repos/devteam/fastqc/fastqc/0.73+galaxy0
    :return: short tool id, e.g. fastqc
    """
    parts = str(tool_id).split("/")
    if len(parts) >= 6 and parts[1] == "repos":
        return parts[4]
    return str(tool_id)


def normalize_value(value):
    """
    Turn a parameter value into a comparable value

    Workflow files and jobs store values differently (e.g. `7`, `"7"` or `"\\"7\\""`,
    connected inputs as `"null"` or `{"__class__": "ConnectedValue"}`), so JSON strings
    are decoded, connected and runtime values become None and scalars become strings.

    :param value: parameter value
    :return: normalized value
    """
    for _ in range(3):
        if not isinstance(value, str):
            break
        try:
            decoded = json.loads(value)
        except ValueError:
            break
        if decoded == value:
            break
        value = decoded
    if isinstance(value, dict):
        if value.get("__class__") in ("ConnectedValue", "RuntimeValue"):
            return None
        return {k: normalize_value(v) for k, v in value.items() if k != "__current_case__"}
    if isinstance(value, list):
        return [normalize_value(v) for v in value]
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value)


def clean_parameters(tool_state):
    """
    Turn the tool state of a workflow step into comparable parameters

    :param tool_state: JSON string with the tool state
    :return: dictionary with parameters
    """
    parameters = json.loads(tool_state) if isinstance(tool_state, str) else dict(tool_state or {})
    for p in IGNORED_PARAMETERS:
        parameters.pop(p, None)
    return {p: normalize_value(v) for p, v in parameters.items()}


def parameter_agreement(ref_step, hist_step):
    """
    Fraction of the reference step parameters with the same value in the history step

    :param ref_step: workflow step of the reference
    :param hist_step: workflow step of the history
    :return: number between 0 and 1
    """
    ref_params = clean_parameters(ref_step.get("tool_state", "{}"))
    hist_params = clean_parameters(hist_step.get("tool_state", "{}"))
    if not ref_params:
        return 1.0
    same = sum(1 for p, v in ref_params.items() if p in hist_params and hist_params[p] == v)
    return same / len(ref_params)


def connection_ids(step):
    """
    Get the indexes of the steps connected to the inputs of a step

    :param step: workflow step
    :return: list of step indexes
    """
    ids = []
    for connection in step.get("input_connections", {}).values():
        for c in connection if isinstance(connection, list) else [connection]:
            if isinstance(c, dict) and "id" in c:
                ids.append(int(c["id"]))
    return ids


def sorted_indexes(steps, inputs):
    """
    Get the indexes of input or tool steps, in step order

    :param steps: workflow steps (dictionary)
    :param inputs: True for input steps, False for tool steps
    :return: sorted list of indexes
    """
    return sorted(int(k) for k, s in steps.items() if is_input_step(s) == inputs)


def match_steps(ref_steps, hist_steps):
    """
    Match the steps of a history to the steps of a reference

    Reference tool steps are taken in order. A history step can match a reference step if
    it uses the same tool. Among them, the preferred one has the most inputs coming from steps
    already matched to the inputs of the reference step, then the most similar parameters, then
    outputs deleted or not like in the reference (i.e. not deleted for usual references), then
    outputs used by other steps, then the same tool version, then the
    same position among the runs of the tool (e.g. the 2nd run with the 2nd run), then the latest
    end time.
    Input steps are matched when they feed matched tool steps, the others by order.

    :param ref_steps: steps of the reference workflow (dictionary)
    :param hist_steps: steps of the history workflow (dictionary)
    :return: dictionary with `mapping` (reference index -> history index), `missing` and `extra` tool step indexes
    """
    ref = {int(k): s for k, s in ref_steps.items()}
    hist = {int(k): s for k, s in hist_steps.items()}
    consumed = {i for s in hist.values() for i in connection_ids(s)}

    def occurrences(steps):
        # position of each tool step among the steps with the same tool
        seen, occ = {}, {}
        for i in sorted_indexes(steps, inputs=False):
            key = tool_key(steps[str(i)]["tool_id"])
            occ[i] = seen.get(key, 0)
            seen[key] = occ[i] + 1
        return occ

    ref_occ, hist_occ = occurrences(ref_steps), occurrences(hist_steps)
    mapping = {}
    used = set()
    for r in sorted_indexes(ref_steps, inputs=False):
        # ignore connections to steps that are not there (e.g. deleted)
        r_prod = [p for p in connection_ids(ref[r]) if p in ref]
        best, best_key = None, None
        for h in sorted_indexes(hist_steps, inputs=False):
            if h in used or tool_key(hist[h]["tool_id"]) != tool_key(ref[r]["tool_id"]):
                continue
            h_prod = [q for q in connection_ids(hist[h]) if q in hist]
            free_inputs = [q for q in h_prod if is_input_step(hist[q]) and q not in used]
            connected = sum(
                1 for p in r_prod
                if (p in mapping and mapping[p] in h_prod) or (p not in mapping and is_input_step(ref[p]) and free_inputs)
            )
            key = (
                connected,
                parameter_agreement(ref[r], hist[h]),
                hist[h].get("deleted", False) == ref[r].get("deleted", False),
                h in consumed,
                hist[h].get("tool_id") == ref[r].get("tool_id"),
                -abs(hist_occ[h] - ref_occ[r]),
                hist[h].get("end_time") or "",
            )
            if best_key is None or key > best_key:
                best, best_key = h, key
        if best is None:
            continue
        mapping[r] = best
        used.add(best)
        # bind the reference inputs of this step to the history inputs of the matched step
        for p in r_prod:
            if p in mapping or not is_input_step(ref[p]):
                continue
            for q in connection_ids(hist[best]):
                if q in hist and is_input_step(hist[q]) and q not in used and hist[q]["type"] == ref[p]["type"]:
                    mapping[p] = q
                    used.add(q)
                    break
    # remaining inputs by order
    free = [q for q in sorted_indexes(hist_steps, inputs=True) if q not in used]
    for p in sorted_indexes(ref_steps, inputs=True):
        if p in mapping:
            continue
        for q in free:
            if hist[q]["type"] == ref[p]["type"]:
                mapping[p] = q
                used.add(q)
                free.remove(q)
                break
    return {
        "mapping": mapping,
        "missing": [r for r in sorted_indexes(ref_steps, inputs=False) if r not in mapping],
        "extra": [h for h in sorted_indexes(hist_steps, inputs=False) if h not in used],
    }


def same_connections(ref_step, hist_step, mapping):
    """
    Check if the inputs of matched steps come from matched steps

    :param ref_step: reference workflow step
    :param hist_step: history workflow step
    :param mapping: reference index -> history index
    :return: boolean
    """
    return {mapping.get(p) for p in connection_ids(ref_step)} == set(connection_ids(hist_step))


def text_similarity(text1, text2):
    """
    Similarity of two texts, line by line

    :param text1: first text
    :param text2: second text
    :return: number between 0 and 1
    """
    if text1 == text2:
        return 1.0
    lines1 = text1.splitlines()[:5000]
    lines2 = text2.splitlines()[:5000]
    if not lines1 or not lines2:
        return 0.0
    return SequenceMatcher(None, lines1, lines2, autojunk=False).ratio()
