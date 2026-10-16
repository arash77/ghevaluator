# Galaxy History Evaluator overview

| Student | Tutorial | Step score | Final output | Missing steps | Extra steps | Copied steps | Job cache | Whole history copied from | Report |
|---|---|---|---|---|---|---|---|---|---|
{%- for row in rows %}
{%- if row.error %}
| {{ row.student }} | {{ row.tutorial }} | error: {{ row.error | replace("|", "\\|") | replace("\n", " ") }} | | | | | | | |
{%- else %}
| {{ row.student }} | {{ row.tutorial }} | {{ row.score.steps }} % | {% if row.score.final_output is not none %}{{ row.score.final_output }} %{% endif %} | {{ row.score.missing_steps }} | {{ row.score.extra_steps }} | {% if row.score.copied_steps %}⚠️ {% endif %}{{ row.score.copied_steps }} | {{ row.score.cached_steps }} | {% if row.score.all_steps_from_history %}⚠️ {{ row.score.all_steps_from_history }}{% endif %} | [report]({{ row.report }}) |
{%- endif %}
{%- endfor %}
