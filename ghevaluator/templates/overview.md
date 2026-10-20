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

How the step score works: every step of the reference is worth 100 points. A step done in the history gets 50 points, 25 more if it was run on the same inputs as in the reference, and up to 25 more for the same settings (each setting counts the same, so 1 different setting out of 4 costs 6.25 points). A missing step gets 0 points. The step score is the average over all steps of the reference. A different tool version is shown but does not lower the score.
