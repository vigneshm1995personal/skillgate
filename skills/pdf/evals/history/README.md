Append-only JSONL written by `skillgate check`. Each line is one run
(`report_to_dict` plus run_id / passed / gate). Gitignore `*.jsonl`.

A read-only pack mount (`docker run -v pack:/pack:ro`) skips history on EACCES.
