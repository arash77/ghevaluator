# Galaxy History Evaluator overview

| Student | Tutorial | Step score | Final result | In short | Report |
|---|---|---|---|---|---|
{%- for row in rows %}
{%- if row.error %}
| {{ row.student | replace("|", "\\|") }} | {{ row.tutorial | replace("|", "\\|") }} | | | ❌ Could not be evaluated: {{ row.error | replace("|", "\\|") | replace("\n", " ") }} | |
{%- else %}
| {{ row.student | replace("|", "\\|") }} | {{ row.tutorial | replace("|", "\\|") }} | {{ row.score.steps }} % | {% if row.score.final_output is not none %}{{ row.score.final_output }} %{% endif %} | {% if row.score.all_steps_from_history or row.score.copied_steps %}⚠️ {% endif %}{{ row.in_short | join(" ") | replace("|", "\\|") }} | [report]({{ row.report }}) |
{%- endif %}
{%- endfor %}

Step score: a missing step counts 0, a step found counts 50 %, plus 25 % if it was run on the right inputs and up to 25 % for its settings.
