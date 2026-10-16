{%- macro yes(value) -%}{% if value %}✅{% else %}❌{% endif %}{%- endmacro -%}
{%- macro cell(value) -%}{{ (value if value is not none else "") | string | replace("|", "\\|") | replace("\n", " ") }}{%- endmacro -%}
# Galaxy History Evaluator report

- Galaxy history: {{ report.inputs.history }}
- Reference {{ report.inputs.reference_type or "workflow" }}: {{ report.inputs.workflow }}
{% if report.score %}
## Summary

| | |
|---|---|
| Step score | {{ report.score.steps }} % |
{%- if report.score.final_output is not none %}
| Final output similarity | {{ report.score.final_output }} % |
{%- endif %}
| Data inputs (reference / history) | {{ report.data_inputs.workflow }} / {{ report.data_inputs.history }} |
| Tool steps (reference / history) | {{ report.steps.workflow }} / {{ report.steps.history }} |
| Missing steps | {{ report.score.missing_steps }} |
| Extra steps (not deleted) | {{ report.score.extra_steps }} |
| Deleted steps | {{ report.score.deleted_steps }} |
| Steps copied from another history | {{ report.score.copied_steps }} |
| Steps from the job cache | {{ report.score.cached_steps }} |

A missing step counts 0. A step found counts 50 %, plus 25 % if its inputs come from the right steps and up to 25 % for its parameters.
{% endif %}
## Steps

| Reference step | Tool | History step | Version (reference / history) | Inputs from right steps | Wrong parameters | Notes |
|---|---|---|---|---|---|---|
{%- for step_num, s in report.comparison_given_reference_workflow_order.items() %}
{%- if s.status == "missing" %}
| {{ s.order.workflow }} | {{ cell(s.tool.workflow) }} | missing | {{ cell(s.version.workflow) }} | | | |
{%- else %}
| {{ s.order.workflow }} | {{ cell(s.tool.workflow) }} | {{ s.order.history }} | {{ cell(s.version.workflow) }} / {{ cell(s.version.history) }} {% if not s.version.same %}⚠️{% endif %} | {{ yes(s.inputs_connection.same) }} | {{ s.parameters.wrong }} / {{ s.parameters.number.workflow }} | {% if s.output_formats and not s.output_formats.same %}output formats {{ s.output_formats.history | join(", ") }} instead of {{ s.output_formats.workflow | join(", ") }}. {% endif %}{% if s.cached %}job cache. {% endif %}{% if s.deleted %}outputs deleted. {% endif %}{% if s.copied_from_history %}copied from history {{ s.copied_from_history }}.{% endif %} |
{%- endif %}
{%- endfor %}
{% for step_num, s in report.comparison_given_reference_workflow_order.items() %}
{%- set wrong = s.parameters.details.items() | rejectattr("1.same") | list %}
{%- if s.status != "missing" and wrong %}
### Step {{ s.order.workflow }} ({{ s.tool.workflow }}): different parameters

| Parameter | Reference | History |
|---|---|---|
{%- for key, value in wrong %}
| {{ cell(key) }} | {{ cell(value.workflow) }} | {{ cell(value.history) }} |
{%- endfor %}
{% endif %}
{%- endfor %}
{%- if report.final_outputs %}
## Final output

Last step of the reference: step {{ report.final_outputs.reference_step.order }}, {{ report.final_outputs.reference_step.tool }} ({{ report.final_outputs.reference_step.formats | join(", ") }}), compared to the last steps of the history.{% if report.final_outputs.note %} Note: {{ report.final_outputs.note }}.{% endif %}

| History step | Tool | Same tool | Same output formats | Content similarity |
|---|---|---|---|---|
{%- for c in report.final_outputs.candidates %}
| {{ c.order }} | {{ cell(c.tool) }} | {{ yes(c.same_tool) }} | {{ yes(c.formats.same) }} | {% if c.content_similarity is not none %}{{ (100 * c.content_similarity) | round(1) }} %{% else %}not compared{% endif %} |
{%- endfor %}
{% endif %}
{%- if report.extra_steps %}
## Steps not in the reference

| History step | Tool | Version | Job cache | Deleted |
|---|---|---|---|---|
{%- for s in report.extra_steps %}
| {{ s.order }} | {{ cell(s.tool) }} | {{ cell(s.version) }} | {% if s.cached %}yes{% endif %} | {% if s.deleted %}yes{% endif %} |
{%- endfor %}
{% endif %}
{%- if report.copied_steps %}
## Steps copied from another history

| History step | Tool | History where the job ran |
|---|---|---|
{%- for s in report.copied_steps %}
| {{ s.order }} | {{ cell(s.tool) }} | {{ s.history }} |
{%- endfor %}
{% endif %}
