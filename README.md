Galaxy History Evaluator
========================

Galaxy History Evaluator or `ghevaluator` is a command-line Python tool to compare Galaxy histories to a reference, a workflow file or another history, and generate JSON, HTML and Markdown reports.

## Context

[Galaxy](https://galaxyproject.org/) is an **open, web-based platform for data-intensive computational research**.

When running their data analysis, Galaxy users create histories storing their data, but also the steps of the data analysis, i.e. the tools used, their versions and parameters.

Galaxy is also used for training where participants follow step-by-step tutorials, stored in Galaxy histories. At the end, participants might want to know if they followed correctly the tutorial and instructors might need to evaluate histories to give feedback and deliver certificates.
**Evaluating histories manually can be painful and error prone**.

Galaxy History Evaluator aims to solve this by providing a command-line tool to compare Galaxy histories to a reference and generate reports with the differences.

## Usage

```bash
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
                        published or shared histories
  -o OUTPUT, --output OUTPUT
                        Path to output folder (default: current folder)
```

Compare a history to the workflow of a [GTN](https://training.galaxyproject.org/) tutorial:

```bash
$ ghevaluator \
    -u "https://usegalaxy.eu/histories/view?id=19b7e0ced2125767" \
    -w "https://training.galaxyproject.org/training-material/topics/introduction/tutorials/galaxy-intro-short/workflows/Galaxy-Workflow-galaxy-intro-short.ga" \
    -o report
```

Compare a history to a reference history:

```bash
$ ghevaluator \
    -u "https://usegalaxy.eu/histories/view?id=892319be4e2b6ca2" \
    -r "https://usegalaxy.eu/histories/view?id=c1ad4cd9d7df4ada" \
    -o report
```

Evaluate several histories listed in a CSV file, e.g. all participants of a training:

```csv
Tutorial name,Ref hist id,Stud hist id,Student name
From Peaks to Genes,c1ad4cd9d7df4ada,892319be4e2b6ca2,Participant 1
```

```bash
$ ghevaluator -c histories.csv -a $GALAXY_API_KEY -o reports
```

The reports of each history are written in a folder named after the student, with an `overview.md` and `overview.json` of all histories.

History URLs can be links with the history id (`/histories/view?id=...`, `/published/history?id=...`) or `/u/<username>/h/<slug>` links of published histories. Histories have to be accessible to the API key owner, e.g. shared with them, or published. Nothing is created or changed in Galaxy.

### What is compared

- **Steps**: steps of the history are matched to the steps of the reference by tool and by the steps their inputs come from, not by their order. Steps run again, run in another order or not in the reference are handled. For each reference step, the report gives the matched history step, the tool version, the parameters and whether its inputs come from the right steps.
- **Missing and extra steps**: reference steps not found in the history, and history steps not in the reference. Steps whose outputs were all deleted are reported but not counted as extra steps.
- **Copied results**: steps whose job ran in another history, i.e. results copied from someone else's history, and steps whose job can not be read, usually because it ran in someone else's private history. When all steps ran in another history, the report says so: this is expected for a history imported by a tutor, not for a history shared by a student.
- **Job cache**: steps whose result was reused from an earlier job.
- **Outputs** (reference history only): output formats of matched steps, and the last step of the reference compared to the last 5 steps of the history (by job end time), including the similarity of the output content for text datasets.

### Score

A missing step counts 0. A step found counts 50 %, plus 25 % if its inputs come from the right steps and up to 25 % for its parameters. The step score is the average over the reference steps. A different tool version is reported but does not change the score.

## Installation

Galaxy History Evaluator can be installed with pip:

```bash
$ pip install ghevaluator
```

## Tests

```bash
$ make test
```

Most tests run offline on histories saved in `tests/data/histories`. A few tests read public histories on usegalaxy.eu and the GTN, and need internet access but no API key.


## Documentation


Documentation could be found at https://streetscience.community/ghevaluator/

To update it:

1. Make the changes in `src/docs`
2. Generate the doc with

    ```bash
    $ make html
    ```