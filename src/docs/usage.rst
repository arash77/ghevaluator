Usage
=====

Galaxy History Evaluator can be used via command-line

.. code-block:: bash

    $ ghevaluator --help
    usage: ghevaluator [-h] [-u HISTORY_URL] [-w WORKFLOW_URL | -r REFERENCE_HISTORY_URL] [-c CSV]
                       [-g GALAXY_URL] [-a APIKEY] [-o OUTPUT]

    Compare Galaxy histories to a reference workflow or history and generate JSON, HTML and Markdown
    reports

    options:
      -h, --help            show this help message and exit
      -u HISTORY_URL, --history_url HISTORY_URL
                            URL to Galaxy history
      -w WORKFLOW_URL, --workflow_url WORKFLOW_URL
                            URL to reference workflow file (.ga)
      -r REFERENCE_HISTORY_URL, --reference_history_url REFERENCE_HISTORY_URL
                            URL to reference Galaxy history
      -c CSV, --csv CSV     CSV file with several histories to evaluate, with columns 'student name',
                            'stud hist id', 'ref hist id' and optional 'tutorial name' (ids or URLs)
      -g GALAXY_URL, --galaxy_url GALAXY_URL
                            Galaxy URL for history ids in the CSV file (default: https://usegalaxy.eu)
      -a APIKEY, --apikey APIKEY
                            Galaxy API key for the same instance where the history is, not needed for
                            published histories or histories shared via link, needed for histories
                            shared with a specific account
      -o OUTPUT, --output OUTPUT
                            Path to output folder (default: current folder)

The tool needs:

1. URL to the history to be evaluated

    A link with the history id (``/histories/view?id=...`` or ``/published/history?id=...``), or the ``/u/<username>/h/<slug>`` link of a published history, as explained in a `dedicated tutorial <https://training.galaxyproject.org/training-material/faqs/galaxy/histories_sharing.html>`_

    For example: https://usegalaxy.eu/histories/view?id=19b7e0ced2125767

2. A reference, either

    - URL to a reference workflow file (``-w``). Links to the workflows of a tutorial are on the tutorial pages of the Galaxy Training website: https://training.galaxyproject.org/

        For example: https://training.galaxyproject.org/training-material/topics/introduction/tutorials/galaxy-intro-short/workflows/Galaxy-Workflow-galaxy-intro-short.ga

    - or URL to a reference history (``-r``). Output formats and the content of the final output are then compared too.

3. Optionally, a Galaxy API key for the Galaxy server where the history is, if the history is not published or shared via link

    To get your own Galaxy API key, please follow the instructions `here <https://training.galaxyproject.org/training-material/faqs/galaxy/preferences_admin_api_key.html>`_

4. Optionally, the path to the folder where the reports should be created

Several histories can be evaluated at once with a CSV file (``-c``) with the columns ``student name``, ``stud hist id``, ``ref hist id`` and optionally ``tutorial name``. History columns can contain history ids (on the Galaxy server given with ``-g``) or URLs, the reference column can also contain a URL to a workflow file.

Nothing is created or changed in Galaxy.


Output
------

For each history, the tool generates:

- ``report.json`` with all the details of the comparison
- ``report.html`` and ``report.md`` with a summary (score, missing and extra steps, copied steps, steps from the job cache), the comparison of each reference step with the matched history step (tool, version, parameters, inputs, output formats) and, with a reference history, the comparison of the final output

With a CSV file, the reports of each history are written in a folder named after the student, with ``overview.md`` and ``overview.json`` for all histories.
